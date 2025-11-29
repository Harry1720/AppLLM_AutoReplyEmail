import os
import logging
from datetime import datetime, timezone
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import create_client
from app.infra.services.gmail_service import GmailService # Import Service dự án

logging.basicConfig(level=logging.INFO)

class EmailVectorizer:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        
        # Kết nối Gmail bằng Token thật của User
        self.gmail = GmailService(token_data)

        # Cấu hình AI & DB
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        
        self.supabase = create_client(
            os.getenv("SUPABASE_URL"), 
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        
        self.vectorstore = SupabaseVectorStore(
            client=self.supabase,
            embedding=self.embeddings,
            table_name="documents",
            query_name="match_documents"
        )

    def sync_user_emails(self):
        logging.info(f"🚀 Bắt đầu đồng bộ Email Đã Gửi (Sent) cho User: {self.user_id}")
        
        # 1. Lấy danh sách 50 email đã gửi gần nhất
        try:
            result = self.gmail.get_emails(max_results=50, folder="SENT") 
            sent_emails = result.get('emails', [])
            
            if not sent_emails:
                logging.info("⚠️ Không tìm thấy email đã gửi nào.")
                return 

            # 2. Xử lý và lưu vào Vector Store
            count = 0
            for email in sent_emails:
                try:
                    # Lấy nội dung chi tiết (HTML Body)
                    detail = self.gmail.get_email_detail(email['id'])
                    if not detail: continue

                    # Chỉ lấy text đơn giản để vector hóa (bỏ qua HTML rườm rà)
                    # (Ở đây ta ghép Subject và Body lại)
                    full_content = f"Subject: {detail['subject']}\nContent: {detail['snippet']}\n{detail['body'][:2000]}"
                    
                    # Chia nhỏ văn bản
                    chunks = self.text_splitter.split_text(full_content)
                    
                    # Tạo metadata để sau này lọc theo user_id
                    metadatas = [{
                        "user_id": self.user_id,
                        "email_id": detail['id'],
                        "subject": detail['subject'],
                        "date": detail['date']
                    } for _ in chunks]

                    # Lưu vào Supabase
                    self.vectorstore.add_texts(texts=chunks, metadatas=metadatas)
                    count += 1
                    print(f"✅ Đã học xong email: {detail['subject'][:30]}...")
                    
                except Exception as e:
                    logging.error(f"Lỗi xử lý email {email['id']}: {e}")

            logging.info(f"🎉 Hoàn tất! Đã học được văn phong từ {count} email.")
            return f"Đã đồng bộ {count} email."

        except Exception as e:
            logging.error(f"Lỗi sync: {e}")
            return str(e)