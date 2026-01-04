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

logging.basicConfig(level=logging.INFO)

# --- CẤU HÌNH STATE ---
class GraphState(TypedDict):
    user_id: str
    target_email_id: str
    current_email: dict
    context_emails: List[str]
    draft_reply: dict
    error: str

# --- CACHE EMBEDDINGS MODEL (LOAD 1 LẦN DUY NHẤT) ---
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
        logging.info("✓ Embeddings Model đã được cache!")
    return _cached_embeddings

class EmailReasoningSystem:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        
        # Kết nối Gmail (Wrapper)
        self.gmail_wrapper = GmailService(token_data)
        self.gmail = self.gmail_wrapper.service # Object gốc để gọi API chuyên sâu
        
        # Kết nối Supabase Draft Repository
        self.draft_repo = DraftRepository()
        
        # Setup AI - GROQ (Cloud)
        # SỬ DỤNG CACHED EMBEDDINGS thay vì tải lại mỗi lần
        self.embeddings = get_embeddings_model()
        
        # CẤU HÌNH GROQ TẠI ĐÂY
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0  # Nhiệt độ 0 để trả lời nhất quán
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
            # Tạo embedding cho query
            query_embedding = self.embeddings.embed_query(query)
            
            # Gọi trực tiếp RPC function match_documents với filter_user_id
            response = self.supabase.rpc(
                'match_documents',
                {
                    'query_embedding': query_embedding,
                    'match_count': 3,
                    'filter_user_id': self.user_id
                }
            ).execute()
            
            # Parse kết quả
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

   # --- NODE 3: VIẾT TRẢ LỜI (FIX LỖI NHÁI & SAI NGÔN NGỮ) ---
    def generate_reply_node(self, state: GraphState) -> GraphState:
        email = state.get("current_email")
        if not email: return state
        
        logging.info("Groq đang suy nghĩ ...")
        
        # Lấy context (nếu không có thì để trống để tránh nhiễu)
        context_str = "\n---\n".join(state["context_emails"]) if state.get("context_emails") else "Không có văn mẫu."
        
        # Instruction mặc định
        instruction = state.get("instruction", "Phản hồi phù hợp và chuyên nghiệp.")

        # --- TEMPLATE MỚI: ÉP NGÔN NGỮ & CHỐNG NHÁI ---
        template = """
        VAI TRÒ CỦA BẠN:
        Bạn là chính tôi (chủ sở hữu email). Bạn đang viết thư trả lời cho người khác.
        KHÔNG ĐƯỢC đóng vai người gửi. KHÔNG ĐƯỢC lặp lại lời người gửi.

        DỮ LIỆU ĐẦU VÀO:
        1. [VĂN PHONG CỦA TÔI] (Tham khảo cách tôi viết):
        {context}
        
        2. [EMAIL NGƯỜI KHÁC GỬI ĐẾN]:
        - Người gửi: {sender}
        - Chủ đề: {subject}
        - Nội dung gốc: "{body}"
        
        3. [YÊU CẦU]: "{instruction}"

        QUY TẮC BẮT BUỘC (TUÂN THỦ TUYỆT ĐỐI):
        
        1. TỰ ĐỘNG PHÁT HIỆN NGÔN NGỮ (QUAN TRỌNG NHẤT):
           - Hãy đọc "Nội dung gốc".
           - Nếu người gửi viết TIẾNG ANH -> Bạn BẮT BUỘC trả lời bằng TIẾNG ANH.
           - Nếu người gửi viết TIẾNG VIỆT -> Bạn BẮT BUỘC trả lời bằng TIẾNG VIỆT.
           - (Bỏ qua ngôn ngữ của phần [VĂN PHONG CỦA TÔI], chỉ quan tâm ngôn ngữ của email mới).

        2. CHỐNG NHÁI (ANTI-PARROTING):
           - Đây là thư "REPLY" (Trả lời).
           - Tuyệt đối KHÔNG chép lại nội dung của người gửi.
           - Ví dụ: Họ hỏi "Khỏe không?", bạn trả lời "Tôi khỏe", KHÔNG ĐƯỢC viết lại "Khỏe không?".
           - Khách nói "Chào bộ phận quản lý" -> ĐÓ LÀ LỜI HỌ NÓI VỚI BẠN.
           - BẠN KHÔNG ĐƯỢC CHÀO LẠI "Chào bộ phận quản lý".
           - BẠN PHẢI CHÀO TÊN HỌ: "Chào {sender}," hoặc "Chào bạn {sender},".

        3. NỘI DUNG (CHI TIẾT & CHUYÊN NGHIỆP):
           - PHẢI viết CHI TIẾT và CỤ THỂ như một email công việc thực tế.
           - HỌC THEO VĂN PHONG CỦA TÔI: Nếu [VĂN PHONG CỦA TÔI] có email tương tự, bắt chước cấu trúc và độ dài của tôi.
           - CẤU TRÚC EMAIL CHUYÊN NGHIỆP (3-5 đoạn văn):
             
             ĐOẠN 1 - MỞ ĐẦU LỊCH SỰ (1-2 câu):
             • Chào hỏi chuyên nghiệp với tên người gửi
             • Cảm ơn hoặc ghi nhận nội dung email của họ
             
             ĐOẠN 2 - THỂ HIỆN HIỂU BIẾT & ĐÁNH GIÁ (2-3 câu):
             • Tóm tắt lại những điểm chính mà người gửi đã đề cập (cho thấy bạn đọc kỹ)
             • Đưa ra ý kiến, đánh giá, hoặc phản hồi ban đầu về đề xuất của họ
             
             ĐOẠN 3 - THÔNG TIN CHI TIẾT & CAM KẾT (3-5 câu):
             • Nêu rõ hành động cụ thể bạn sẽ làm (xem xét, đánh giá, phân tích...)
             • Đề cập các yếu tố quan trọng cần xem xét
             • Nếu cần thông tin thêm, YÊU CẦU CỤ THỂ (không chung chung)
             
             ĐOẠN 4 - ĐỀ XUẤT BƯỚC TIẾP THEO (nếu phù hợp - 1-2 câu):
             • Đề xuất lịch họp cụ thể (nếu cần): "Tôi có thể sắp xếp vào [thời gian gợi ý]"
             • Hoặc hứa liên hệ lại trong khung thời gian cụ thể
             
             ĐOẠN 5 - KẾT THÚC (1 câu):
             • Câu kết lịch sự, chuyên nghiệp
             • Ký tên: "Trân trọng," hoặc tương đương

           - ĐỘ DÀI TỐI THIỂU: 150-250 từ (khoảng 5-8 câu văn hoàn chỉnh)
           - SỬ DỤNG PLACEHOLDER CHO THÔNG TIN KHÔNG BIẾT:
             • Thời gian: "[Time]" hoặc "[Thời gian phù hợp]"
             • Ngày: "[Date]" hoặc "[Ngày cụ thể]"  
             • Tên công ty/sản phẩm: Dùng tên từ email gốc
           - TRÁNH TUYỆT ĐỐI: Câu trả lời chung chung, ngắn gọn 1-2 dòng, thiếu nội dung cụ thể

        4. THÁI ĐỘ (Dựa trên nội dung):
           - Nếu khách đang giận (khiếu nại) -> Hãy xin lỗi, nhún nhường, xưng "Em/Mình" hoặc "Chúng tôi".
           - Nếu là công việc -> Chuyên nghiệp, trang trọng, có chiều sâu.
           - Nếu là bạn bè -> Thân mật, vui vẻ.
           - Nếu không rõ -> Trung lập, lịch sự.


        ĐỊNH DẠNG OUTPUT (JSON ONLY):
        Chỉ trả về JSON hợp lệ. Không được có bất kỳ dòng chữ nào khác bên ngoài JSON.
        {{
            "subject": "Tiêu đề thư (Thêm 'Re:' phía trước tiêu đề gốc)",
            "body": "Nội dung thư trả lời (Định dạng HTML, xuống dòng dùng <br>)"
        }}
        """
        
        # Lấy nội dung đầy đủ hơn để LLM có đủ ngữ cảnh viết chi tiết
        body_content = email.get('body', '')[:2500] # Tăng từ 1000 lên 2500 ký tự

        prompt = PromptTemplate.from_template(template).format(
            context=context_str,
            sender=email.get('from', 'Someone'),
            subject=email.get('subject', 'No Subject'),
            body=body_content, 
            instruction=instruction 
        )
        
        try:
            # Gọi Groq
            response = self.llm.invoke(prompt)
            
            # ChatGroq trả về AIMessage object, cần lấy content
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Xử lý làm sạch JSON (LLM hay thêm ```json ở đầu)
            response_clean = response_text.strip()
            if "```json" in response_clean:
                response_clean = response_clean.split("```json")[1].split("```")[0]
            elif "```" in response_clean:
                response_clean = response_clean.split("```")[1].split("```")[0]
            
            # Parse JSON
            draft = json.loads(response_clean.strip())
            return {**state, "draft_reply": draft}
            
        except Exception as e:
            logging.error(f"Lỗi Groq Gen: {e}")
            return {**state, "draft_reply": {
                "subject": f"Re: {email.get('subject')}",
                "body": "Xin lỗi, hệ thống AI đang bận. Vui lòng thử lại sau."
            }}
        

    # --- NODE 4: TẠO BẢN NHÁP (ĐÃ SỬA ĐỂ GẮN VÀO THREAD) ---
    def create_draft_node(self, state: GraphState) -> GraphState:
        draft = state.get("draft_reply")
        email = state.get("current_email")
        
        if draft and email:
            logging.info("Đang tạo Draft Reply trong Thread...")
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
                
                # QUAN TRỌNG: Gắn Thread References để Gmail hiểu đây là Reply
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
                logging.info(f"Đã tạo Draft Reply trong Thread! Draft ID: {draft_id}")
                
                # 6. LƯU DRAFT VÀO SUPABASE
                try:
                    # Lấy thông tin người nhận và thread_id
                    recipient_email = email.get("from", "")
                    thread_id = original_msg.get('threadId', '')
                    
                    # Lưu vào bảng email_drafts với schema đầy đủ
                    supabase_draft = self.draft_repo.create_draft(
                        user_id=self.user_id,     
                        email_id=email['id'],     
                        thread_id=thread_id,       
                        draft_id=draft_id,        
                        subject=draft.get("subject", ""),
                        body=draft.get("body", ""),
                        recipient=recipient_email
                    )
                    
                    if supabase_draft:
                        logging.info(f"Draft đã được lưu vào Supabase với ID: {supabase_draft.get('id')}")
                    else:
                        logging.warning("Không thể lưu draft vào Supabase (không chặn workflow)")
                        
                except Exception as e:
                    logging.error(f"Lỗi lưu draft vào Supabase: {e} (tiếp tục workflow)")
                
                # CẬP NHẬT: Trả về draft_id trong state
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