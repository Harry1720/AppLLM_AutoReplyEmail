from app.infra.supabase_client import get_supabase
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.domain.entities.draft_entity import DraftEntity

logging.basicConfig(level=logging.INFO)

def get_vietnam_time():
    """Trả về thời gian hiện tại theo múi giờ Việt Nam (UTC+7)"""
    return datetime.now(timezone.utc) + timedelta(hours=7)

class DraftRepository:
    
    def __init__(self):
        self.db = get_supabase()
        self.table_name = "email_drafts"
    
    # Bây giờ Python đã hiểu DraftEntity là một Class
    def create_draft(self, draft: DraftEntity) -> Optional[DraftEntity]:
   
        try:
            # Chuẩn bị dữ liệu
            draft_data = draft.model_dump(exclude={"id"}) 
            if not draft_data.get("created_at"):
                draft_data["created_at"] = get_vietnam_time().isoformat()
            
            res = self.db.table(self.table_name).upsert(draft_data).execute()
            
            if res.data and len(res.data) > 0:
                created_draft = DraftEntity(**res.data[0]) 
                logging.info(f"Draft đã lưu. ID: {created_draft.id}")
                return created_draft
            return None
            
        except Exception as e:
            logging.error(f"Lỗi tạo draft trong Supabase: {e}")
            return None
    
    def get_draft_by_gmail_id(self, gmail_draft_id: str) -> Optional[DraftEntity]:
        try:
            res = self.db.table(self.table_name).select("*").eq("draft_id", gmail_draft_id).execute()
            
            if res.data and len(res.data) > 0:
                return DraftEntity(**res.data[0]) 
            return None
            
        except Exception as e:
            logging.error(f"Lỗi tìm draft: {e}")
            return None
    
    def delete_draft_by_gmail_id(self, gmail_draft_id: str) -> bool:
        try:
            delete_res = self.db.table(self.table_name).delete().eq("draft_id", gmail_draft_id).execute()
            
            if delete_res.data and len(delete_res.data) > 0:
                return True
            else:
                return False
            
        except Exception as e:
            logging.error(f"Lỗi xóa draft: {e}")
            return False
    
    def check_draft_exists(self, gmail_draft_id: str) -> bool:
        try:
            res = self.db.table(self.table_name).select("id").eq("draft_id", gmail_draft_id).execute()
            return bool(res.data and len(res.data) > 0)
        except Exception as e:
            logging.error(f"Lỗi kiểm tra draft: {e}")
            return False
    
    def get_all_drafts_by_user(self, user_id: str, status: str = None) -> List[DraftEntity]:
        try:
            query = self.db.table(self.table_name).select("*").eq("user_id", user_id)
            
            if status:
                query = query.eq("status", status)
            
            res = query.execute()
            
            if res.data:
                drafts = [DraftEntity(**item) for item in res.data]
                return drafts
            return []
            
        except Exception as e:
            logging.error(f"Lỗi lấy drafts: {e}")
            return []
    
    def update_status(self, gmail_draft_id: str, new_status: str) -> bool:
        try:
            update_res = self.db.table(self.table_name).update({
                "status": new_status
            }).eq("draft_id", gmail_draft_id).execute()
            return bool(update_res.data)
        except Exception as e:
            logging.error(f"Lỗi update status: {e}")
            return False

    def update_draft_content(self, gmail_draft_id: str, subject: str, body: str, recipient: str) -> bool:
        try:
            update_res = self.db.table(self.table_name).update({
                "subject": subject,
                "body": body,
                "recipient": recipient
            }).eq("draft_id", gmail_draft_id).execute()
            return bool(update_res.data)
        except Exception as e:
            logging.error(f"Lỗi cập nhật nội dung: {e}")
            return False
            
    def get_sent_email_ids(self, user_id: str) -> List[str]:
        try:
            res = self.db.table(self.table_name).select("email_id")\
                .eq("user_id", user_id).eq("status", "sent").execute()
            if res.data:
                return [item["email_id"] for item in res.data]
            return []
        except Exception as e:
            logging.error(f"Lỗi lấy sent email IDs: {e}")
            return []