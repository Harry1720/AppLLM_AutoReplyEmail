import logging
from app.infra.supabase_client import get_supabase
from app.infra.ai.vectorizer import EmailVectorizer
from app.infra.services.gmail_service import GmailService

class CheckAndAutoSyncUseCase:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        self.token_data = token_data
        self.db = get_supabase()

        self.vectorizer = EmailVectorizer(user_id, token_data)

    def execute(self):
        try:
            # 1. Đếm số lượng document trong DB
            response = self.db.table("documents").select("id", count="exact").eq("metadata->>user_id", self.user_id).execute()
            doc_count = response.count if hasattr(response, 'count') else 0
            
            # 2. Kiểm tra email mới từ Gmail
            gmail_service = GmailService(self.token_data)
            result = gmail_service.get_emails(max_results=50, folder="SENT")
            sent_emails = result.get('emails', [])
            
            if not sent_emails:
                return {
                    "synced": doc_count > 0,
                    "document_count": doc_count,
                    "pending_emails": 0,
                    "message": "Không tìm thấy email đã gửi nào"
                }

            # 3. So sánh với DB để tìm email chưa sync
            existing_email_ids = self.vectorizer._get_existing_email_ids()
            new_email_ids = [e['id'] for e in sent_emails if e['id'] not in existing_email_ids]
            pending_count = len(new_email_ids)
            
            # 4. TỰ ĐỘNG SYNC NẾU CÓ EMAIL MỚI
            if pending_count > 0:
                logging.info(f"🔄 [UseCase] Phát hiện {pending_count} email mới, đang tự động sync...")
                sync_result = self.vectorizer.sync_user_emails()
                
                # Đếm lại sau khi sync
                response_after = self.db.table("documents").select("id", count="exact").eq("metadata->>user_id", self.user_id).execute()
                new_doc_count = response_after.count if hasattr(response_after, 'count') else 0
                
                return {
                    "synced": True,
                    "document_count": new_doc_count,
                    "pending_emails": 0,
                    "just_synced": sync_result.get("synced_count", 0),
                    "message": f"✓ Đã tự động đồng bộ {sync_result.get('synced_count', 0)} email mới"
                }
            else:
                return {
                    "synced": True,
                    "document_count": doc_count,
                    "pending_emails": 0,
                    "message": "✓ Dữ liệu đã được đồng bộ hoàn toàn"
                }
                
        except Exception as e:
            logging.error(f" [UseCase] Lỗi check status: {e}")
            # Fallback an toàn
            return {
                "synced": False,
                "document_count": 0,
                "message": f"Lỗi kiểm tra: {str(e)}"
            }