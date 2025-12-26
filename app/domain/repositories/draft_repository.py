from app.infra.supabase_client import get_supabase
import logging

logging.basicConfig(level=logging.INFO)

class DraftRepository:
    """Repository để quản lý bảng email_drafts trong Supabase
    
    Schema: id, draft_id, subject, body, recipient, created_at
    """
    
    def __init__(self):
        self.db = get_supabase()
    
    def create_draft(self, user_id: str, email_id: str, thread_id: str, draft_id: str, subject: str, body: str, recipient: str):
        """
        Tạo mới một draft trong Supabase
        
        Args:
            user_id: ID của user (required - NOT NULL constraint)
            email_id: Gmail Message ID của email gốc đang reply (required - NOT NULL constraint)
            thread_id: Gmail Thread ID của email conversation (required - NOT NULL constraint)
            draft_id: Gmail Draft ID (unique identifier)
            subject: Tiêu đề email
            body: Nội dung draft (HTML/text)
            recipient: Email người nhận
        
        Returns:
            Dict: Thông tin draft đã tạo hoặc None nếu lỗi
        """
        try:
            draft_data = {
                "user_id": user_id,
                "email_id": email_id,
                "thread_id": thread_id,
                "draft_id": draft_id,
                "subject": subject,
                "body": body,
                "recipient": recipient,
                "status": "draft"  # Trạng thái mặc định
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
        """
        Lấy draft từ Supabase dựa trên Gmail Draft ID
        
        Args:
            gmail_draft_id: ID của draft trên Gmail
        
        Returns:
            Dict hoặc None
        """
        try:
            res = self.db.table("email_drafts").select("*").eq("draft_id", gmail_draft_id).execute()
            
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
            
        except Exception as e:
            logging.error(f"Lỗi tìm draft: {e}")
            return None
    
    def delete_draft_by_gmail_id(self, gmail_draft_id: str):
        """
        Xóa draft khỏi Supabase dựa trên Gmail Draft ID
        
        Args:
            gmail_draft_id: ID của draft trên Gmail
        
        Returns:
            Bool: True nếu thành công, False nếu thất bại
        """
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
        """
        Kiểm tra xem draft đã tồn tại chưa
        
        Args:
            gmail_draft_id: Gmail Draft ID
        
        Returns:
            Bool: True nếu đã tồn tại, False nếu chưa
        """
        try:
            res = self.db.table("email_drafts").select("id").eq("draft_id", gmail_draft_id).execute()
            return res.data and len(res.data) > 0
            
        except Exception as e:
            logging.error(f"Lỗi kiểm tra draft: {e}")
            return False
    
    def get_all_drafts_by_user(self, user_id: str, status: str = None):
        """
        Lấy tất cả drafts của một user từ Supabase
        
        Args:
            user_id: ID của user
            status: Lọc theo status ('draft', 'sent', 'deleted') - None để lấy tất cả
        
        Returns:
            List[Dict]: Danh sách các drafts hoặc []
        """
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
        """
        Cập nhật status của draft
        
        Args:
            gmail_draft_id: Gmail Draft ID
            new_status: Status mới ('draft', 'sent', 'deleted')
        
        Returns:
            Bool: True nếu thành công, False nếu thất bại
        """
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
        """
        Lấy danh sách email_id đã được gửi (status='sent')
        
        Args:
            user_id: ID của user
        
        Returns:
            List[str]: Danh sách email_id đã gửi
        """
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
        """
        Cập nhật nội dung draft trong Supabase (subject, body, recipient)
        
        Args:
            gmail_draft_id: Gmail Draft ID
            subject: Tiêu đề mới
            body: Nội dung mới
            recipient: Email người nhận mới
        
        Returns:
            Bool: True nếu thành công, False nếu thất bại
        """
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