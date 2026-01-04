from app.infra.supabase_client import get_supabase
import logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)

# Helper function để lấy giờ Việt Nam
def get_vietnam_time():
    """Trả về thời gian hiện tại theo múi giờ Việt Nam (UTC+7)"""
    return datetime.now(timezone.utc) + timedelta(hours=7)

class DraftRepository:
    
    def __init__(self):
        self.db = get_supabase()
    
    def create_draft(self, user_id: str, email_id: str, thread_id: str, draft_id: str, subject: str, body: str, recipient: str):
   
        try:
            draft_data = {
                "user_id": user_id,
                "email_id": email_id,
                "thread_id": thread_id,
                "draft_id": draft_id,
                "subject": subject,
                "body": body,
                "recipient": recipient,
                "status": "draft",  # Trạng thái mặc định
                "created_at": get_vietnam_time().isoformat()  # Set giờ Việt Nam
            }
            
            res = self.db.table("email_drafts").insert(draft_data).execute()
            
            if res.data and len(res.data) > 0:
                logging.info(f"Draft đã được lưu vào Supabase. Supabase ID: {res.data[0].get('id')}, Gmail Draft ID: {draft_id}")
                return res.data[0]
            return None
            
        except Exception as e:
            logging.error(f"Lỗi tạo draft trong Supabase: {e}")
            return None
    
    def get_draft_by_gmail_id(self, gmail_draft_id: str):
  
        try:
            res = self.db.table("email_drafts").select("*").eq("draft_id", gmail_draft_id).execute()
            
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
            
        except Exception as e:
            logging.error(f"Lỗi tìm draft: {e}")
            return None
    
    def delete_draft_by_gmail_id(self, gmail_draft_id: str):
  
        try:
            delete_res = self.db.table("email_drafts").delete().eq("draft_id", gmail_draft_id).execute()
            
            if delete_res.data and len(delete_res.data) > 0:
                logging.info(f"Đã xóa draft khỏi Supabase. Gmail Draft ID: {gmail_draft_id}")
                return True
            else:
                logging.warning(f"Không tìm thấy draft với Gmail Draft ID: {gmail_draft_id}")
                return False
            
        except Exception as e:
            logging.error(f"Lỗi xóa draft: {e}")
            return False
    
    def check_draft_exists(self, gmail_draft_id: str):
    
        try:
            res = self.db.table("email_drafts").select("id").eq("draft_id", gmail_draft_id).execute()
            return res.data and len(res.data) > 0
            
        except Exception as e:
            logging.error(f"Lỗi kiểm tra draft: {e}")
            return False
    
    def get_all_drafts_by_user(self, user_id: str, status: str = None):
    
        try:
            query = self.db.table("email_drafts").select("*").eq("user_id", user_id)
            
            if status:
                query = query.eq("status", status)
            
            res = query.execute()
            
            if res.data:
                logging.info(f"Tìm thấy {len(res.data)} drafts cho user {user_id} (status={status or 'all'})")
                return res.data
            return []
            
        except Exception as e:
            logging.error(f"Lỗi lấy drafts: {e}")
            return []
    
    def update_status(self, gmail_draft_id: str, new_status: str):
   
        try:
            update_res = self.db.table("email_drafts").update({
                "status": new_status
            }).eq("draft_id", gmail_draft_id).execute()
            
            if update_res.data and len(update_res.data) > 0:
                logging.info(f"Đã update status draft {gmail_draft_id} -> {new_status}")
                return True
            else:
                logging.warning(f"Không tìm thấy draft với Gmail Draft ID: {gmail_draft_id}")
                return False
            
        except Exception as e:
            logging.error(f"Lỗi update status draft: {e}")
            return False
    
    def get_sent_email_ids(self, user_id: str):
      
        try:
            res = self.db.table("email_drafts").select("email_id").eq("user_id", user_id).eq("status", "sent").execute()
            
            if res.data:
                email_ids = [draft["email_id"] for draft in res.data]
                logging.info(f"User {user_id} đã gửi {len(email_ids)} email")
                return email_ids
            return []
            
        except Exception as e:
            logging.error(f"Lỗi lấy sent email IDs: {e}")
            return []
    
    def update_draft_content(self, gmail_draft_id: str, subject: str, body: str, recipient: str):
       
        try:
            update_res = self.db.table("email_drafts").update({
                "subject": subject,
                "body": body,
                "recipient": recipient
            }).eq("draft_id", gmail_draft_id).execute()
            
            if update_res.data and len(update_res.data) > 0:
                logging.info(f"Đã cập nhật nội dung draft {gmail_draft_id} trong Supabase")
                return True
            else:
                logging.warning(f"Không tìm thấy draft với Gmail Draft ID: {gmail_draft_id}")
                return False
            
        except Exception as e:
            logging.error(f"Lỗi cập nhật nội dung draft: {e}")
            return False