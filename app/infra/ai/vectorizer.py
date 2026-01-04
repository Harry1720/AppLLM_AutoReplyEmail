import os
import logging
from datetime import datetime, timezone, timedelta
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import create_client
from app.infra.services.gmail_service import GmailService # Import Service dự án
import uuid

logging.basicConfig(level=logging.INFO)

# Cache embeddings model globally
_cached_vectorizer_embeddings = None

def get_vectorizer_embeddings():
    global _cached_vectorizer_embeddings
    if _cached_vectorizer_embeddings is None:
        logging.info("[Vectorizer] Đang tải Embeddings Model...")
        _cached_vectorizer_embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logging.info("[Vectorizer] ✓ Embeddings Model đã được cache!")
    return _cached_vectorizer_embeddings

class EmailVectorizer:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        
        self.gmail = GmailService(token_data)

        # Cấu hình AI & DB - Sử dụng cached embeddings
        self.embeddings = get_vectorizer_embeddings()
        # Giảm chunk_overlap từ 100 -> 50 để tăng tốc
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=50)
        
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
        try:
            result = self.gmail.get_emails(max_results=50, folder="SENT") 
            sent_emails = result.get('emails', [])
            
            if not sent_emails:
                logging.info("Không tìm thấy email đã gửi nào.")
                return {"synced_count": 0, "skipped_count": 0, "message": "Không có email"}

            existing_email_ids = self._get_existing_email_ids()
            logging.info(f"Đã có {len(existing_email_ids)} email trong database")

            # Lọc email mới trước
            new_emails = [e for e in sent_emails if e['id'] not in existing_email_ids]
            skipped_count = len(sent_emails) - len(new_emails)
            
            if not new_emails:
                logging.info(f"Tất cả {len(sent_emails)} email đều đã tồn tại trong database")
                return {
                    "synced_count": 0,
                    "skipped_count": skipped_count,
                    "message": "Không có email mới"
                }
            
            logging.info(f"Tìm thấy {len(new_emails)} email mới cần vector hóa")

            # Xử lý batch embedding cho tất cả chunks cùng lúc
            all_chunks = []
            all_metadatas = []
            synced_count = 0
            
            for email in new_emails:
                try:
                    email_id = email['id']
                    
                    # Lấy nội dung chi tiết
                    detail = self.gmail.get_email_detail(email_id)
                    if not detail: 
                        continue

                    # Chỉ lấy text đơn giản
                    full_content = f"Subject: {detail['subject']}\nContent: {detail['snippet']}\n{detail['body'][:2000]}"
                    
                    # Chia nhỏ văn bản
                    chunks = self.text_splitter.split_text(full_content)
                    
                    # Tạo metadata
                    metadata = {
                        "user_id": self.user_id,
                        "email_id": detail['id'],
                        "subject": detail['subject'],
                        "date": detail['date']
                    }
                    
                    all_chunks.extend(chunks)
                    all_metadatas.extend([metadata for _ in chunks])
                    
                    synced_count += 1
                    
                except Exception as e:
                    logging.error(f"Lỗi xử lý email {email.get('id', 'unknown')}: {e}")
            
            # BATCH EMBEDDING - Tạo embedding cho tất cả chunks cùng lúc (nhanh hơn nhiều)
            if all_chunks:
                logging.info(f"Đang tạo embeddings cho {len(all_chunks)} chunks...")
                try:
                    # embed_documents() nhanh hơn nhiều so với gọi embed_query() từng cái
                    all_embeddings = self.embeddings.embed_documents(all_chunks)
                    
                    # Batch insert vào Supabase
                    logging.info(f"Đang lưu {len(all_chunks)} chunks vào database...")
                    batch_data = []
                    for i, (chunk, metadata, embedding) in enumerate(zip(all_chunks, all_metadatas, all_embeddings)):
                        batch_data.append({
                            "id": str(uuid.uuid4()),
                            "content": chunk,
                            "metadata": metadata,
                            "embedding": embedding,
                            "user_id": self.user_id
                        })
                    
                    # Insert theo batch 10 records để tránh timeout
                    batch_size = 10
                    for i in range(0, len(batch_data), batch_size):
                        batch = batch_data[i:i + batch_size]
                        self.supabase.table("documents").insert(batch).execute()
                    
                    logging.info(f"✓ Đã lưu xong {len(all_chunks)} chunks cho {synced_count} email mới")
                    
                except Exception as e:
                    logging.error(f"Lỗi batch embedding/insert: {e}")
                    raise

            logging.info(f"Hoàn tất! Đã học {synced_count} email mới, bỏ qua {skipped_count} email đã có.")
            return {
                "synced_count": synced_count,
                "skipped_count": skipped_count,
                "message": f"Đã đồng bộ {synced_count} email mới"
            }

        except Exception as e:
            logging.error(f"Lỗi sync: {e}")
            return {"synced_count": 0, "skipped_count": 0, "error": str(e)}
    
    def _get_existing_email_ids(self):
        try:
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
            logging.error(f"Lỗi lấy danh sách email đã có: {e}")
            return set()  # Trả về set rỗng nếu lỗi (sẽ sync tất cả)