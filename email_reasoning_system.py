from langgraph.graph import StateGraph
from typing import Dict, List, TypedDict
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from gmail_reader import get_gmail_service
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class EmailReasoningState(TypedDict):
    new_email: Dict
    relevant_emails: List[Dict]
    context: str
    draft_reply: str
    final_reply: str
    confidence_score: float

class EmailReasoningSystem:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=os.getenv('GOOGLE_API_KEY')
        )
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.3
        )
        
        self.vectorstore = Chroma(
            collection_name="emails",
            embedding_function=self.embeddings,
            persist_directory="./vector_db"
        )
        
        self.gmail_service = get_gmail_service()

    def read_new_email(self, state: EmailReasoningState) -> EmailReasoningState:
        """Đọc email mới đến (inbox)"""
        logging.info("📧 Đọc email mới từ inbox...")
        
        try:
            # Lấy email chưa đọc từ inbox
            results = self.gmail_service.users().messages().list(
                userId='me', 
                q='is:unread in:inbox',
                maxResults=1
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logging.info("Không có email mới")
                return state
            
            # Lấy email mới nhất
            message_id = messages[0]['id']
            msg = self.gmail_service.users().messages().get(
                userId='me', 
                id=message_id
            ).execute()
            
            # Parse email
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'No Sender')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')
            
            # Extract body
            body = self._extract_email_body(msg['payload'])
            
            state["new_email"] = {
                'id': message_id,
                'subject': subject,
                'from': sender,
                'date': date,
                'body': body,
                'snippet': msg.get('snippet', '')
            }
            
            logging.info(f"✓ Đã đọc email mới: {subject}")
            return state
            
        except Exception as e:
            logging.error(f"Lỗi khi đọc email: {str(e)}")
            return state

    def _extract_email_body(self, payload):
        """Extract email body từ payload"""
        body = ''
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        import base64
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
        else:
            if payload['body'].get('data'):
                import base64
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body

    def find_relevant_past_emails(self, state: EmailReasoningState) -> EmailReasoningState:
        """Tìm các email đã gửi liên quan từ vector database"""
        logging.info("🔍 Tìm kiếm email liên quan...")
        
        if not state.get("new_email"):
            return state
        
        try:
            new_email = state["new_email"]
            
            # Tạo query từ subject và body của email mới
            query_text = f"{new_email['subject']} {new_email['body']}"
            
            # Tìm kiếm các chunk tương tự
            similar_docs = self.vectorstore.similarity_search_with_score(
                query_text, 
                k=5  # Lấy 5 kết quả tương tự nhất
            )
            
            relevant_emails = []
            seen_email_ids = set()
            
            for doc, score in similar_docs:
                metadata = doc.metadata
                email_id = metadata.get('email_id')
                
                # Tránh trùng lặp email
                if email_id not in seen_email_ids:
                    relevant_emails.append({
                        'email_id': email_id,
                        'subject': metadata.get('subject', ''),
                        'from': metadata.get('from', ''),
                        'to': metadata.get('to', ''),
                        'date': metadata.get('date', ''),
                        'content': doc.page_content,
                        'similarity_score': float(1 - score)  # Convert distance to similarity
                    })
                    seen_email_ids.add(email_id)
            
            state["relevant_emails"] = relevant_emails
            
            logging.info(f"✓ Tìm thấy {len(relevant_emails)} email liên quan")
            for email in relevant_emails:
                logging.info(f"  - {email['subject']} (similarity: {email['similarity_score']:.2f})")
            
            return state
            
        except Exception as e:
            logging.error(f"Lỗi khi tìm kiếm: {str(e)}")
            state["relevant_emails"] = []
            return state

    def create_context(self, state: EmailReasoningState) -> EmailReasoningState:
        """Tạo ngữ cảnh từ các email liên quan"""
        logging.info("📝 Tạo ngữ cảnh...")
        
        relevant_emails = state.get("relevant_emails", [])
        
        if not relevant_emails:
            state["context"] = "Không có email tương tự trong lịch sử."
            return state
        
        context_parts = []
        for i, email in enumerate(relevant_emails, 1):
            context_parts.append(f"""
EMAIL ĐÃ GỬI #{i}:
Tiêu đề: {email['subject']}
Người nhận: {email['to']}
Ngày: {email['date']}
Nội dung: {email['content'][:500]}...
Độ tương tự: {email['similarity_score']:.2f}
---""")
        
        state["context"] = "\n".join(context_parts)
        logging.info(f"✓ Đã tạo ngữ cảnh từ {len(relevant_emails)} email")
        
        return state

    def draft_reply_with_llm(self, state: EmailReasoningState) -> EmailReasoningState:
        """Sử dụng LLM để tạo bản nháp trả lời"""
        logging.info("🤖 Tạo bản nháp trả lời với Gemini...")
        
        new_email = state.get("new_email")
        context = state.get("context", "")
        
        if not new_email:
            logging.error("Không có email mới để trả lời")
            return state
        
        # Tạo prompt engineering
        prompt = f"""Bạn là một trợ lý email thông minh và chuyên nghiệp. 
Nhiệm vụ: Dựa vào email mới nhận và các email tôi đã từng gửi trong quá khứ, hãy soạn một email trả lời phù hợp.

NGUYÊN TẮC:
- Giữ văn phong nhất quán với các email đã gửi trước đây
- Trả lời đúng trọng tâm câu hỏi
- Lịch sự, chuyên nghiệp
- Ngắn gọn, súc tích
- Sử dụng tiếng Việt tự nhiên

---
EMAIL MỚI NHẬN:
Từ: {new_email['from']}
Tiêu đề: {new_email['subject']}
Nội dung: {new_email['body']}

---
CÁC EMAIL TÔI ĐÃ GỬI TRƯỚC ĐÂY (để tham khảo văn phong):
{context}

---
HÃY SOẠN EMAIL TRẢ LỜI:
Chỉ trả về nội dung email, không cần tiêu đề hay thông tin khác."""

        try:
            response = self.llm.invoke(prompt)
            draft_reply = response.content.strip()
            
            state["draft_reply"] = draft_reply
            
            # Đánh giá độ tin cậy dựa trên context
            confidence = min(0.9, 0.5 + len(state.get("relevant_emails", [])) * 0.1)
            state["confidence_score"] = confidence
            
            logging.info(f"✓ Đã tạo bản nháp (confidence: {confidence:.2f})")
            logging.info(f"Preview: {draft_reply[:100]}...")
            
            return state
            
        except Exception as e:
            logging.error(f"Lỗi khi gọi LLM: {str(e)}")
            state["draft_reply"] = f"Lỗi: Không thể tạo bản nháp. {str(e)}"
            state["confidence_score"] = 0.0
            return state

    def review_draft(self, state: EmailReasoningState) -> EmailReasoningState:
        """Xem xét và hoàn thiện bản nháp"""
        logging.info("👀 Xem xét bản nháp...")
        
        draft = state.get("draft_reply", "")
        confidence = state.get("confidence_score", 0.0)
        
        # Thêm disclaimer nếu confidence thấp
        if confidence < 0.6:
            final_reply = f"{draft}\n\n[Lưu ý: Email này được tạo tự động, vui lòng kiểm tra trước khi gửi]"
        else:
            final_reply = draft
        
        state["final_reply"] = final_reply
        
        logging.info(f"✓ Hoàn thành bản nháp cuối cùng")
        return state

def create_reasoning_workflow():
    """Tạo workflow với LangGraph"""
    system = EmailReasoningSystem()
    
    # Tạo state graph
    workflow = StateGraph(EmailReasoningState)
    
    # Thêm các nodes
    workflow.add_node("read_email", system.read_new_email)
    workflow.add_node("find_relevant", system.find_relevant_past_emails)
    workflow.add_node("create_context", system.create_context)
    workflow.add_node("draft_reply", system.draft_reply_with_llm)
    workflow.add_node("review", system.review_draft)
    
    # Định nghĩa luồng
    workflow.set_entry_point("read_email")
    workflow.add_edge("read_email", "find_relevant")
    workflow.add_edge("find_relevant", "create_context")
    workflow.add_edge("create_context", "draft_reply")
    workflow.add_edge("draft_reply", "review")
    
    return workflow.compile()

def main():
    """Chạy hệ thống reasoning"""
    logging.info("🚀 Khởi động Email Reasoning System...")
    
    try:
        # Tạo workflow
        app = create_reasoning_workflow()
        
        # Khởi tạo state rỗng
        initial_state = EmailReasoningState(
            new_email={},
            relevant_emails=[],
            context="",
            draft_reply="",
            final_reply="",
            confidence_score=0.0
        )
        
        # Chạy workflow
        final_state = app.invoke(initial_state)
        
        # Hiển thị kết quả
        print("\n" + "="*60)
        print("📧 KẾT QUẢ EMAIL REASONING SYSTEM")
        print("="*60)
        
        if final_state.get("new_email"):
            new_email = final_state["new_email"]
            print(f"\n📨 EMAIL MỚI NHẬN:")
            print(f"Từ: {new_email['from']}")
            print(f"Tiêu đề: {new_email['subject']}")
            print(f"Nội dung: {new_email['body'][:200]}...")
        
        print(f"\n🔍 ĐÃ TÌM THẤY: {len(final_state.get('relevant_emails', []))} email liên quan")
        
        print(f"\n🤖 BẢN NHÁP TRẢ LỜI:")
        print(f"Độ tin cậy: {final_state.get('confidence_score', 0):.1%}")
        print("-" * 40)
        print(final_state.get('final_reply', 'Không có bản nháp'))
        print("-" * 40)
        
        return final_state
        
    except Exception as e:
        logging.error(f"Lỗi hệ thống: {str(e)}")
        return None

if __name__ == "__main__":
    result = main()