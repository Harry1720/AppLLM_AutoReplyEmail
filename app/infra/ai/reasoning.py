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
from app.domain.repositories.draft_repository import DraftRepository

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
        
        # Kết nối Supabase Draft Repository
        self.draft_repo = DraftRepository()
        
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
            # Sử dụng match_documents function của Supabase thay vì filter
            # Vì SupabaseVectorStore có issue với filter params
            docs = self.vectorstore.similarity_search(query, k=3)
            
            # Lọc kết quả theo user_id sau khi query
            filtered_docs = [d for d in docs if d.metadata.get("user_id") == self.user_id]
            
            context = [d.page_content for d in filtered_docs]
            logging.info(f"✅ Tìm thấy {len(context)} email tham khảo")
            return {**state, "context_emails": context}
        except Exception as e:
            logging.warning(f"⚠️ Lỗi RAG: {e}. Tiếp tục không có context.")
            return {**state, "context_emails": []}

   # --- NODE 3: VIẾT TRẢ LỜI (OLLAMA) - ĐÃ NÂNG CẤP ---
    def generate_reply_node(self, state: GraphState) -> GraphState:
        email = state.get("current_email")
        if not email: return state
        
        logging.info("🧠 Ollama đang suy nghĩ...")
        
        # Lấy các biến từ State
        context_str = "\n---\n".join(state["context_emails"]) if state.get("context_emails") else "Không có văn mẫu."
        instruction = state.get("instruction", "Hãy trả lời một cách lịch sự, chuyên nghiệp.")

        # --- TEMPLATE CAO CẤP (Xử lý instruction + RAG) ---
        template = """
        VAI TRÒ:
        Bạn là Thư ký AI riêng của tôi. Nhiệm vụ của bạn là soạn thảo email trả lời.

        DỮ LIỆU ĐẦU VÀO:
        
        1. [VĂN PHONG THAM KHẢO] (Cách tôi thường viết mail):
        {context}
        --------------------------------------------------

        2. [EMAIL CẦN TRẢ LỜI]:
        - Người gửi: {sender}
        - Chủ đề: {subject}
        - Tóm tắt: {snippet}
        - Nội dung chính: {body}
        --------------------------------------------------

        3. [YÊU CẦU CỦA TÔI] (QUAN TRỌNG NHẤT - BẮT BUỘC TUÂN THỦ):
        "{instruction}"
        *(Ví dụ: Nếu tôi bảo "Từ chối", bạn phải viết thư từ chối, dù văn phong tham khảo có nhiệt tình đến đâu)*.
        --------------------------------------------------

        NGUYÊN TẮC SOẠN THẢO:
        1. NGÔN NGỮ: Email đến là tiếng gì (Anh/Việt) thì trả lời bằng tiếng đó.
        2. GIỌNG ĐIỆU: Bắt chước cách xưng hô trong [VĂN PHONG THAM KHẢO]. Nếu không có, dùng giọng lịch sự.
        3. TRUNG THỰC: Tuyệt đối KHÔNG tự bịa ra ngày giờ, số điện thoại. Nếu thiếu thông tin, hãy để: [ĐIỀN NGÀY], [ĐIỀN SỐ]...

        ĐỊNH DẠNG ĐẦU RA (JSON FORMAT ONLY):
        Chỉ trả về chuỗi JSON, không giải thích thêm.
        {{
            "subject": "Tiêu đề thư trả lời (Thường bắt đầu bằng Re: ...)",
            "body": "Nội dung thư (định dạng HTML cơ bản, xuống dòng dùng <br>)"
        }}
        """
        
        # Format dữ liệu vào Template
        prompt = PromptTemplate.from_template(template).format(
            context=context_str,
            sender=email['from'],
            subject=email['subject'],
            snippet=email['snippet'],
            # Lấy 1500 ký tự đầu của Body để AI hiểu sâu hơn (nếu có)
            body=email.get('body', '')[:1500], 
            instruction=instruction # <--- Truyền yêu cầu (Đồng ý/Từ chối) vào đây
        )
        
        try:
            # Gọi Ollama
            response = self.llm.invoke(prompt)
            
            # Xử lý kết quả trả về (Lọc sạch Markdown nếu có)
            # Ollama hay trả về kiểu: ```json { ... } ``` nên cần clean
            response_clean = str(response).strip()
            if response_clean.startswith('```json'):
                response_clean = response_clean[7:]
            if response_clean.endswith('```'):
                response_clean = response_clean[:-3]
                
            draft = json.loads(response_clean.strip())
            return {**state, "draft_reply": draft}
            
        except Exception as e:
            logging.error(f"Lỗi Ollama Gen: {e}")
            # Fallback an toàn nếu AI lỗi
            return {**state, "draft_reply": {
                "subject": f"Re: {email['subject']}",
                "body": f"Chào bạn,<br>Tôi đã nhận được email về việc: {instruction}.<br>Tôi sẽ phản hồi sớm.<br>Trân trọng."
            }}

    # --- NODE 4: TẠO BẢN NHÁP (ĐÃ SỬA ĐỂ GẮN VÀO THREAD) ---
    def create_draft_node(self, state: GraphState) -> GraphState:
        draft = state.get("draft_reply")
        email = state.get("current_email")
        
        if draft and email:
            logging.info("📝 Đang tạo Draft Reply trong Thread...")
            try:
                # 1. Lấy thông tin email gốc chi tiết hơn để có Message-ID
                original_msg = self.gmail.users().messages().get(
                    userId='me', 
                    id=email['id'], 
                    format='metadata'
                ).execute()
                
                payload = original_msg.get('payload', {})
                headers_list = payload.get('headers', [])
                headers = {h['name']: h['value'] for h in headers_list}
                
                # 2. Lấy người nhận (từ người gửi email gốc)
                recipient = email['from']
                if '<' in recipient: 
                    recipient = recipient.split('<')[1].replace('>', '')

                # 3. Tạo message với Thread references
                message = MIMEText(draft['body'], 'html', 'utf-8')
                message['to'] = recipient
                message['subject'] = draft['subject']
                
                # ⭐ QUAN TRỌNG: Gắn Thread References để Gmail hiểu đây là Reply
                msg_id_header = headers.get('Message-ID')
                if msg_id_header:
                    message['In-Reply-To'] = msg_id_header
                    message['References'] = msg_id_header
                
                # 4. Encode và tạo Draft
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                
                body = {
                    'message': {
                        'raw': raw,
                        'threadId': original_msg.get('threadId')  # ⭐ Gắn Thread ID
                    }
                }
                
                # 5. Gọi API tạo Draft
                draft_result = self.gmail.users().drafts().create(
                    userId='me', 
                    body=body
                ).execute()
                
                draft_id = draft_result['id']
                logging.info(f"✅ Đã tạo Draft Reply trong Thread! Draft ID: {draft_id}")
                
                # 6. LƯU DRAFT VÀO SUPABASE
                try:
                    # Lấy thông tin người nhận
                    recipient_email = email.get("from", "")
                    
                    # Lưu vào bảng email_drafts với schema mới
                    supabase_draft = self.draft_repo.create_draft(
                        draft_id=draft_id,  # Gmail Draft ID
                        subject=draft.get("subject", ""),
                        body=draft.get("body", ""),
                        recipient=recipient_email
                    )
                    
                    if supabase_draft:
                        logging.info(f"✅ Draft đã được lưu vào Supabase với ID: {supabase_draft.get('id')}")
                    else:
                        logging.warning("⚠️ Không thể lưu draft vào Supabase (không chặn workflow)")
                        
                except Exception as e:
                    logging.error(f"❌ Lỗi lưu draft vào Supabase: {e} (tiếp tục workflow)")
                
                # ⭐ CẬP NHẬT: Trả về draft_id trong state
                updated_draft = {**draft, "draft_id": draft_id}
                return {**state, "draft_reply": updated_draft}
                
            except Exception as e:
                logging.error(f"❌ Lỗi tạo draft reply: {e}")
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