from langgraph.graph import StateGraph, END
from typing import List, TypedDict, Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from supabase.client import create_client
import os
import json
import logging
import base64
from email.mime.text import MIMEText
from app.infra.services.gmail_service import GmailService
from app.domain.repositories.draft_repository import DraftRepository
from app.domain.entities.draft_entity import DraftEntity

logging.basicConfig(level=logging.INFO)

# --- CẤU HÌNH STATE ---
class GraphState(TypedDict):
    user_id: str
    target_email_id: str
    current_email: dict
    context_emails: List[str]
    draft_reply: dict
    error: str

_cached_embeddings = None

def get_embeddings_model():
    global _cached_embeddings
    if _cached_embeddings is None:
        logging.info("Đang tải Embeddings Model lần đầu...")
        _cached_embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logging.info(" Embeddings Model đã được cache!")
    return _cached_embeddings

class EmailReasoningSystem:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        
        # Kết nối Gmail (Wrapper)
        self.gmail_wrapper = GmailService(token_data)
        self.gmail = self.gmail_wrapper.service 
        
        # Kết nối Supabase Draft Repository
        self.draft_repo = DraftRepository()
        
        # Setup AI - GROQ (Cloud)
        self.embeddings = get_embeddings_model()
        
        # CẤU HÌNH GROQ TẠI ĐÂY
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0 
        ).bind(response_format={"type": "json_object"})
        
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
        logging.info(f"[Groq] Bắt đầu xử lý email ID: {msg_id}")
        
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
        
        logging.info("Đang tìm kiếm văn phong cũ trong Supabase...")
        query = f"{email['subject']} {email['body'][:200]}"
        
        try:
            query_embedding = self.embeddings.embed_query(query)
            
            response = self.supabase.rpc(
                'match_documents',
                {
                    'query_embedding': query_embedding,
                    'match_count': 3,
                    'filter_user_id': self.user_id
                }
            ).execute()
            
            context = []
            if response.data:
                for doc in response.data:
                    context.append(doc.get('content', ''))
                logging.info(f"Tìm thấy {len(context)} email tham khảo từ user {self.user_id}")
            else:
                logging.info("Không tìm thấy email tham khảo nào")
            
            return {**state, "context_emails": context}
        except Exception as e:
            logging.warning(f"Lỗi RAG: {e}. Tiếp tục không có context.")
            return {**state, "context_emails": []}

    # --- NODE 3: VIẾT TRẢ LỜI ---
    def generate_reply_node(self, state: GraphState) -> GraphState:
        email = state.get("current_email")
        if not email: return state
        
        logging.info("Groq đang suy nghĩ ...")
        
        context_str = "\n---\n".join(state["context_emails"]) if state.get("context_emails") else "Không có văn mẫu."
        instruction = state.get("instruction", "Phản hồi phù hợp và chuyên nghiệp.")

        template = """
        VAI TRÒ CỦA BẠN:
        Bạn là chính tôi (chủ sở hữu email). Bạn đang viết thư trả lời cho người khác.
        KHÔNG ĐƯỢC đóng vai người gửi. KHÔNG ĐƯỢC lặp lại lời người gửi.

        DỮ LIỆU ĐẦU VÀO:
        1. [VĂN PHONG CỦA TÔI]: {context}
        2. [EMAIL NGƯỜI KHÁC GỬI ĐẾN]:
           - Người gửi: {sender}
           - Chủ đề: {subject}
           - Nội dung gốc: "{body}"
        3. [YÊU CẦU]: "{instruction}"

        QUY TẮC BẮT BUỘC:
        1. NGÔN NGỮ: Nếu khách viết Anh -> Trả lời Anh. Khách viết Việt -> Trả lời Việt.
        2. CHỐNG NHÁI: KHÔNG lặp lại câu hỏi của khách.
        3. CẤU TRÚC: Chào hỏi -> Tóm tắt ý hiểu -> Phản hồi chi tiết -> Đề xuất tiếp theo -> Kết thư.
        4. OUTPUT FORMAT (JSON ONLY):
        {{
            "subject": "Tiêu đề thư",
            "body": "Nội dung HTML (dùng <br> để xuống dòng)"
        }}
        """
        
        body_content = email.get('body', '')[:2500]

        prompt = PromptTemplate.from_template(template).format(
            context=context_str,
            sender=email.get('from', 'Someone'),
            subject=email.get('subject', 'No Subject'),
            body=body_content, 
            instruction=instruction 
        )
        
        try:
            response = self.llm.invoke(prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            response_clean = response_text.strip()
            if "```json" in response_clean:
                response_clean = response_clean.split("```json")[1].split("```")[0]
            elif "```" in response_clean:
                response_clean = response_clean.split("```")[1].split("```")[0]
            
            draft = json.loads(response_clean.strip())
            return {**state, "draft_reply": draft}
            
        except Exception as e:
            logging.error(f"Lỗi Groq Gen: {e}")
            return {**state, "draft_reply": {
                "subject": f"Re: {email.get('subject')}",
                "body": "Xin lỗi, hệ thống AI đang bận. Vui lòng thử lại sau."
            }}
        

    # --- NODE 4: TẠO BẢN NHÁP ---
    def create_draft_node(self, state: GraphState) -> GraphState:
        draft = state.get("draft_reply")
        email = state.get("current_email")
        
        if draft and email:
            logging.info("Đang tạo Draft Reply trong Thread...")
            try:
                # 1. Lấy thông tin email gốc
                original_msg = self.gmail.users().messages().get(
                    userId='me', 
                    id=email['id'], 
                    format='metadata'
                ).execute()
                
                payload = original_msg.get('payload', {})
                headers_list = payload.get('headers', [])
                headers = {h['name']: h['value'] for h in headers_list}
                
                # 2. Lấy người nhận
                recipient = email['from']
                if '<' in recipient: 
                    recipient = recipient.split('<')[1].replace('>', '')

                # 3. Tạo message MIMEText
                message = MIMEText(draft['body'], 'html', 'utf-8')
                message['to'] = recipient
                message['subject'] = draft['subject']
                
                msg_id_header = headers.get('Message-ID')
                if msg_id_header:
                    message['In-Reply-To'] = msg_id_header
                    message['References'] = msg_id_header
                
                # 4. Encode
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                body = {
                    'message': {
                        'raw': raw,
                        'threadId': original_msg.get('threadId')
                    }
                }
                
                # 5. Gọi API Gmail
                draft_result = self.gmail.users().drafts().create(
                    userId='me', 
                    body=body
                ).execute()
                
                draft_id = draft_result['id']
                logging.info(f"Đã tạo Draft Reply trong Thread! Draft ID: {draft_id}")
                
                # 6. LƯU DRAFT VÀO SUPABASE (Entity)
                try:
                    recipient_email = email.get("from", "")
                    thread_id = original_msg.get('threadId', '')
                    
                    # Tạo Entity (Không truyền id vì nó là Optional)
                    new_draft_entity = DraftEntity(
                        user_id=self.user_id,
                        email_id=email['id'],
                        thread_id=thread_id,
                        draft_id=draft_id,
                        subject=draft.get("subject", ""),
                        body=draft.get("body", ""),
                        recipient=recipient_email,
                        status="draft"
                    )
                    
                    # Lưu vào DB
                    supabase_draft = self.draft_repo.create_draft(new_draft_entity)
                    
                    if supabase_draft:
                        logging.info(f"Draft đã được lưu vào Supabase với ID: {supabase_draft.id}")
                    else:
                        logging.warning("Không thể lưu draft vào Supabase")
                        
                except Exception as e:
                    logging.error(f"Lỗi lưu draft vào Supabase: {e} (tiếp tục workflow)")
                
                updated_draft = {**draft, "draft_id": draft_id}
                return {**state, "draft_reply": updated_draft}
                
            except Exception as e:
                logging.error(f"Lỗi tạo draft reply: {e}")
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