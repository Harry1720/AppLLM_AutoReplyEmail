from langgraph.graph import StateGraph, END
from typing import List, TypedDict, Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM # <--- Dùng thư viện Ollama
from langchain_core.prompts import PromptTemplate
from supabase.client import create_client
import os
import json
import logging
import base64
from email.mime.text import MIMEText
from app.infra.services.gmail_service import GmailService

logging.basicConfig(level=logging.INFO)

# --- CẤU HÌNH STATE ---
class GraphState(TypedDict):
    user_id: str
    target_email_id: str
    current_email: dict
    context_emails: List[str]
    draft_reply: dict
    error: str

class EmailReasoningSystem:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        
        # Kết nối Gmail (Wrapper)
        self.gmail_wrapper = GmailService(token_data)
        self.gmail = self.gmail_wrapper.service # Object gốc để gọi API chuyên sâu
        
        # Setup AI - OLLAMA (Local)
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # 👇 CẤU HÌNH OLLAMA TẠI ĐÂY
        # Yêu cầu: Bạn phải đang chạy 'ollama serve' và đã pull model 'llama3'
        self.llm = OllamaLLM(
            model="llama3",
            format="json", # Bắt buộc trả về JSON
            temperature=0  # Nhiệt độ 0 để trả lời nhất quán
        )
        
        self.supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
        self.vectorstore = SupabaseVectorStore(
            client=self.supabase, 
            embedding=self.embeddings, 
            table_name="documents", 
            query_name="match_documents"
        )

    # --- NODE 1: LẤY NỘI DUNG EMAIL ---
    def fetch_email_node(self, state: GraphState) -> GraphState:
        msg_id = state.get("target_email_id")
        logging.info(f"🚀 [Ollama] Bắt đầu xử lý email ID: {msg_id}")
        
        if not msg_id:
            return {**state, "error": "Không có ID email"}

        try:
            detail = self.gmail_wrapper.get_email_detail(msg_id)
            if not detail:
                return {**state, "error": "Không tìm thấy email"}
            
            return {**state, "current_email": detail}
        except Exception as e:
            return {**state, "error": str(e)}

    # --- NODE 2: TÌM KIẾM VĂN PHONG CŨ (RAG) ---
    def retrieve_context_node(self, state: GraphState) -> GraphState:
        email = state.get("current_email")
        if not email: return state
        
        logging.info("🔍 Đang tìm kiếm văn phong cũ trong Supabase...")
        query = f"{email['subject']} {email['body'][:200]}"
        
        try:
            docs = self.vectorstore.similarity_search(
                query, k=3, filter={"user_id": self.user_id}
            )
            context = [d.page_content for d in docs]
            return {**state, "context_emails": context}
        except Exception as e:
            logging.warning(f"Lỗi RAG: {e}")
            return {**state, "context_emails": []}

    # --- NODE 3: VIẾT TRẢ LỜI (OLLAMA) ---
    def generate_reply_node(self, state: GraphState) -> GraphState:
        email = state.get("current_email")
        if not email: return state
        
        logging.info("🧠 Ollama đang suy nghĩ...")
        
        context_str = "\n---\n".join(state["context_emails"]) if state["context_emails"] else "Không có."

        template = """Bạn là trợ lý ảo chuyên nghiệp.
        Nhiệm vụ: Soạn email trả lời bằng Tiếng Việt dựa trên thông tin sau.
        
        VĂN PHONG THAM KHẢO:
        {context}
        
        EMAIL CẦN TRẢ LỜI:
        Từ: {sender}
        Chủ đề: {subject}
        Nội dung: {snippet}
        
        YÊU CẦU ĐẦU RA (JSON format):
        {{
            "subject": "Tiêu đề thư trả lời (có Re:)",
            "body": "Nội dung thư trả lời (lịch sự, ngắn gọn)"
        }}
        """
        
        prompt = PromptTemplate.from_template(template).format(
            context=context_str,
            sender=email['from'],
            subject=email['subject'],
            snippet=email['snippet']
        )
        
        try:
            response = self.llm.invoke(prompt)
            
            # Xử lý chuỗi JSON từ Ollama (đôi khi nó kèm markdown ```json)
            response_clean = str(response).strip()
            if response_clean.startswith('```json'):
                response_clean = response_clean[7:]
            if response_clean.endswith('```'):
                response_clean = response_clean[:-3]
                
            draft = json.loads(response_clean)
            return {**state, "draft_reply": draft}
            
        except Exception as e:
            logging.error(f"Lỗi Ollama: {e}")
            return {**state, "draft_reply": {
                "subject": f"Re: {email['subject']}",
                "body": "Xin lỗi, AI gặp lỗi khi xử lý định dạng JSON."
            }}

    # --- NODE 4: TẠO BẢN NHÁP ---
    def create_draft_node(self, state: GraphState) -> GraphState:
        draft = state.get("draft_reply")
        email = state.get("current_email")
        
        if draft and email:
            logging.info("📝 Đang tạo Draft trên Gmail...")
            try:
                # Lấy email người nhận
                recipient = email['from']
                if '<' in recipient: recipient = recipient.split('<')[1].replace('>', '')

                # Tạo message raw
                message = MIMEText(draft['body'], 'html', 'utf-8')
                message['to'] = recipient
                message['subject'] = draft['subject']
                
                # Threading (Trả lời đúng luồng)
                # Dùng hàm get của dict để tránh lỗi nếu key không tồn tại
                # Trong GmailService get_email_detail ta chưa lấy message_id gốc, 
                # nên tạm thời chỉ set threadId (vẫn gom nhóm được)
                
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                
                body = {
                    'message': {'raw': raw},
                    'threadId': email.get('id') # threadId thường giống id nếu là mail đầu
                }
                
                # Gọi API Gmail qua object gốc
                self.gmail.users().drafts().create(userId='me', body=body).execute()
                logging.info("✅ Tạo Draft thành công!")
                
            except Exception as e:
                logging.error(f"Lỗi tạo draft: {e}")
                return {**state, "error": str(e)}
            
        return state

# --- WORKFLOW ---
def create_single_email_workflow(user_id: str, token_data: dict):
    system = EmailReasoningSystem(user_id, token_data)
    wf = StateGraph(GraphState)
    
    wf.add_node("fetch", system.fetch_email_node)
    wf.add_node("rag", system.retrieve_context_node)
    wf.add_node("gen", system.generate_reply_node)
    wf.add_node("draft", system.create_draft_node)
    
    wf.set_entry_point("fetch")
    wf.add_edge("fetch", "rag")
    wf.add_edge("rag", "gen")
    wf.add_edge("gen", "draft")
    wf.add_edge("draft", END)
    
    return wf.compile()