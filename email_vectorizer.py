import os
import sys
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import Client, create_client
from gmail_reader import get_sent_emails

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Tải biến môi trường (.env)
load_dotenv()

class EmailVectorizer:
    def __init__(self, user_id: str):
        self.user_id = user_id
        
        # Khởi tạo embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Khởi tạo bộ chia văn bản
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", "!", "?", " ", ""]
        )
        
        # Khởi tạo Supabase
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            logging.error("❌ SUPABASE_URL và SUPABASE_SERVICE_KEY chưa được đặt trong .env")
            sys.exit(1)

        self.supabase_client = create_client(supabase_url, supabase_key)
        
        # Khởi tạo vector store
        self.vectorstore = SupabaseVectorStore(
            client=self.supabase_client,
            embedding=self.embeddings,
            table_name="documents",
            query_name="match_documents"
        )

    def get_user_last_sync(self) -> datetime:
        """Lấy thời gian đồng bộ lần cuối của người dùng"""
        try:
            result = self.supabase_client.table("users").select("last_synced_at").eq("id", self.user_id).execute()
            if result.data and result.data[0].get("last_synced_at"):
                return datetime.fromisoformat(result.data[0]["last_synced_at"].replace("Z", "+00:00"))
            return datetime(1970, 1, 1, tzinfo=timezone.utc)  # Thời gian khởi tạo cho lần đồng bộ đầu tiên
        except Exception as e:
            logging.warning(f"Lỗi khi lấy thời gian đồng bộ lần cuối: {e}")
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    def update_user_last_sync(self):
        """Cập nhật thời gian đồng bộ lần cuối của người dùng"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            self.supabase_client.table("users").update({"last_synced_at": now}).eq("id", self.user_id).execute()
            logging.info("✓ Đã cập nhật thời gian đồng bộ lần cuối của người dùng")
        except Exception as e:
            logging.warning(f"Lỗi khi cập nhật thời gian đồng bộ: {e}")

    def get_existing_email_ids(self) -> set:
        """Lấy danh sách ID email đã tồn tại của người dùng"""
        try:
            result = self.supabase_client.table("documents").select("metadata").eq("metadata->>user_id", self.user_id).execute()
            existing_ids = set()
            for row in result.data:
                if row.get("metadata", {}).get("email_id"):
                    existing_ids.add(row["metadata"]["email_id"])
            return existing_ids
        except Exception as e:
            logging.warning(f"Lỗi khi lấy danh sách ID email đã tồn tại: {e}")
            return set()

    def filter_new_emails(self, emails: list, last_sync: datetime) -> list:
        """Lọc ra các email mới kể từ lần đồng bộ cuối"""
        existing_ids = self.get_existing_email_ids()
        new_emails = []
        
        for email in emails:
            email_id = email.get('id', f'unknown_{len(new_emails)}')
            
            # Bỏ qua nếu đã tồn tại
            if email_id in existing_ids:
                continue
            
            new_emails.append(email)
        
        return new_emails

    def sync_user_emails(self, incremental: bool = True):
        """Đồng bộ email cho một người dùng cụ thể"""
        logging.info(f"🚀 Bắt đầu đồng bộ email cho người dùng: {self.user_id}")
        
        # Lấy thời gian đồng bộ lần cuối nếu là đồng bộ gia tăng
        last_sync = None
        if incremental:
            last_sync = self.get_user_last_sync()
            logging.info(f"Lần đồng bộ cuối: {last_sync}")

        # Lấy email
        logging.info("📧 Đang lấy email đã gửi...")
        try:
            all_emails = get_sent_emails()
            logging.info(f"✓ Đã lấy {len(all_emails)} email đã gửi")
        except Exception as e:
            logging.error(f"❌ Lỗi khi lấy email: {e}")
            return

        # Lọc email mới
        if incremental:
            emails_to_process = self.filter_new_emails(all_emails, last_sync)
            logging.info(f"📊 Tìm thấy {len(emails_to_process)} email mới để xử lý")
        else:
            emails_to_process = all_emails
            logging.info(f"📊 Đang xử lý tất cả {len(emails_to_process)} email (đồng bộ đầy đủ)")

        if not emails_to_process:
            logging.info("✅ Không có email mới để xử lý")
            return

        # Xử lý email
        logging.info("⏳ Bắt đầu vector hóa...")
        count_chunks = 0
        
        for i, email in enumerate(emails_to_process):
            try:
                logging.info(f"  -> Đang xử lý email {i+1}/{len(emails_to_process)}: {email['subject'][:40]}...")
                
                full_content = f"""
From: {email['from']}
To: {email['to']}
Subject: {email['subject']}
Date: {email['date']}

{email['body']}
"""
                chunks = self.text_splitter.split_text(full_content)
                
                # Tạo metadata với user_id
                metadatas = [{
                    "user_id": self.user_id,  # Quan trọng: Thêm user_id vào metadata
                    "email_id": email.get('id', f'unknown_{i}'),
                    "subject": email.get('subject', 'Không có tiêu đề'),
                    "from": email.get('from', 'Người gửi không xác định'),
                    "to": email.get('to', 'Người nhận không xác định'),
                    "date": email.get('date', 'Không có ngày'),
                    "chunk_id": chunk_index
                } for chunk_index in range(len(chunks))]

                # Thêm vào vector store
                self.vectorstore.add_texts(texts=chunks, metadatas=metadatas)
                count_chunks += len(chunks)
                
            except Exception as e:
                logging.warning(f"  ⚠️ Lỗi khi xử lý email {email.get('id')}: {e}")

        # Cập nhật thời gian đồng bộ lần cuối
        if incremental:
            self.update_user_last_sync()

        # Kết quả
        logging.info("\n" + "="*50)
        logging.info("✅ ĐỒNG BỘ EMAIL HOÀN TẤT!")
        logging.info(f"ID người dùng: {self.user_id}")
        logging.info(f"Số lượng email đã xử lý: {len(emails_to_process)}")
        logging.info(f"Số lượng chunks đã tạo: {count_chunks}")
        logging.info(f"Loại đồng bộ: {'Gia tăng' if incremental else 'Đầy đủ'}")
        logging.info("="*50)

def sync_user_emails_api(user_id: str, full_sync: bool = False):
    """Hàm API để đồng bộ email người dùng"""
    try:
        vectorizer = EmailVectorizer(user_id)
        vectorizer.sync_user_emails(incremental=not full_sync)
        return {"success": True, "message": "Đã hoàn thành đồng bộ email"}
    except Exception as e:
        logging.error(f"Đồng bộ email thất bại cho người dùng {user_id}: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Ví dụ sử dụng
    import sys
    
    if len(sys.argv) < 2:
        print("Cách sử dụng: python email_vectorizer_improved.py <user_id> [--full-sync]")
        sys.exit(1)
    
    user_id = sys.argv[1]
    full_sync = "--full-sync" in sys.argv
    
    result = sync_user_emails_api(user_id, full_sync)
    print(f"Kết quả: {result}")