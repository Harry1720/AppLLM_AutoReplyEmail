import os
import logging
import uuid
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
                return {"synced_count": 0, "skipped_count": 0, "message": "Không có email"}

            # 2. Kiểm tra email nào đã được vector hóa
            existing_email_ids = self._get_existing_email_ids()
            logging.info(f"📊 Đã có {len(existing_email_ids)} email trong database")

            # 3. Xử lý và lưu vào Vector Store (chỉ email mới)
            synced_count = 0
            skipped_count = 0
            
            for email in sent_emails:
                try:
                    email_id = email['id']
                    
                    # Kiểm tra xem email đã tồn tại chưa
                    if email_id in existing_email_ids:
                        skipped_count += 1
                        logging.info(f"⏭️ Bỏ qua email đã có: {email.get('subject', 'No Subject')[:30]}...")
                        continue
                    
                    # Lấy nội dung chi tiết (HTML Body)
                    detail = self.gmail.get_email_detail(email_id)
                    if not detail: 
                        continue

                    # Chỉ lấy text đơn giản để vector hóa (bỏ qua HTML rườm rà)
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

                    # Debug log để kiểm tra user_id
                    logging.info(f"🔍 Đang lưu email với user_id: {self.user_id}")
                    
                    # Lưu trực tiếp vào Supabase thay vì dùng vectorstore
                    # để kiểm soát chính xác user_id được insert
                    for i, chunk in enumerate(chunks):
                        # Tạo embedding cho chunk
                        embedding = self.embeddings.embed_query(chunk)
                        
                        # Insert trực tiếp vào table với user_id chính xác
                        doc_data = {
                            "id": str(uuid.uuid4()),  # Generate UUID for id column
                            "content": chunk,
                            "metadata": metadatas[i],
                            "embedding": embedding,
                            "user_id": self.user_id  # Đảm bảo user_id ở cấp độ cột
                        }
                        
                        try:
                            self.supabase.table("documents").insert(doc_data).execute()
                        except Exception as insert_error:
                            logging.error(f"❌ Lỗi insert chunk {i}: {insert_error}")
                            raise
                    
                    synced_count += 1
                    logging.info(f"✅ Đã học xong email: {detail['subject'][:30]}... (ID: {email_id})")
                    
                except Exception as e:
                    logging.error(f"❌ Lỗi xử lý email {email.get('id', 'unknown')}: {e}")

            logging.info(f"🎉 Hoàn tất! Đã học {synced_count} email mới, bỏ qua {skipped_count} email đã có.")
            return {
                "synced_count": synced_count,
                "skipped_count": skipped_count,
                "message": f"Đã đồng bộ {synced_count} email mới"
            }

        except Exception as e:
            logging.error(f"❌ Lỗi sync: {e}")
            return {"synced_count": 0, "skipped_count": 0, "error": str(e)}
    
    def _get_existing_email_ids(self):
        """
        Lấy danh sách email_id đã được vector hóa trong Supabase cho user hiện tại
        
        Returns:
            set: Tập hợp các email_id đã tồn tại
        """
        try:
            # Query trực tiếp từ Supabase để lấy danh sách email_id
            response = self.supabase.table("documents").select("metadata").eq("metadata->>user_id", self.user_id).execute()
            
            existing_ids = set()
            if response.data:
                for doc in response.data:
                    metadata = doc.get("metadata", {})
                    email_id = metadata.get("email_id")
                    if email_id:
                        existing_ids.add(email_id)
            
            return existing_ids
            
        except Exception as e:
            logging.error(f"❌ Lỗi lấy danh sách email đã có: {e}")
            return set()  # Trả về set rỗng nếu lỗi (sẽ sync tất cả)