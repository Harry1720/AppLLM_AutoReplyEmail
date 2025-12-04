from app.infra.supabase_client import get_supabase
import logging

logging.basicConfig(level=logging.INFO)

class DraftRepository:
    """Repository để quản lý bảng email_drafts trong Supabase"""
    
    def __init__(self):
        self.db = get_supabase()
    
    def create_draft(self, user_id: str, email_id: str, content: str, metadata: dict = None, embedding: list = None):
        """
        Tạo mới một draft trong Supabase
        
        Args:
            user_id: ID của user
            email_id: ID của email gốc (email cần reply)
            content: Nội dung draft (HTML/text)
            metadata: Dict chứa thông tin bổ sung (subject, to, from, draft_id từ Gmail, etc.)
            embedding: Vector embedding của nội dung (optional)
        
        Returns:
            Dict: Thông tin draft đã tạo hoặc None nếu lỗi
        """
        try:
            draft_data = {
                "user_id": user_id,
                "email_id": email_id,
                "content": content,
                "metadata": metadata or {},
                "embedding": embedding
            }
            
            res = self.db.table("email_drafts").insert(draft_data).execute()
            
            if res.data and len(res.data) > 0:
                logging.info(f"✅ Draft đã được lưu vào Supabase. Draft ID: {res.data[0].get('id')}")
                return res.data[0]
            return None
            
        except Exception as e:
            logging.error(f"❌ Lỗi tạo draft trong Supabase: {e}")
            return None
    
    def get_draft_by_gmail_id(self, gmail_draft_id: str):
        """
        Lấy draft từ Supabase dựa trên Gmail Draft ID
        
        Args:
            gmail_draft_id: ID của draft trên Gmail (lưu trong metadata)
        
        Returns:
            Dict hoặc None
        """
        try:
            # Tìm draft có metadata chứa gmail_draft_id
            res = self.db.table("email_drafts").select("*").execute()
            
            if res.data:
                for draft in res.data:
                    metadata = draft.get("metadata", {})
                    if metadata.get("gmail_draft_id") == gmail_draft_id:
                        return draft
            return None
            
        except Exception as e:
            logging.error(f"❌ Lỗi tìm draft: {e}")
            return None
    
    def get_draft_by_email_id(self, email_id: str, user_id: str):
        """
        Lấy draft theo email_id và user_id
        
        Args:
            email_id: ID của email gốc
            user_id: ID của user
        
        Returns:
            Dict hoặc None
        """
        try:
            res = self.db.table("email_drafts").select("*").eq("email_id", email_id).eq("user_id", user_id).execute()
            
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
            
        except Exception as e:
            logging.error(f"❌ Lỗi lấy draft: {e}")
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
            # Tìm và xóa draft
            res = self.db.table("email_drafts").select("*").execute()
            
            if res.data:
                for draft in res.data:
                    metadata = draft.get("metadata", {})
                    if metadata.get("gmail_draft_id") == gmail_draft_id:
                        delete_res = self.db.table("email_drafts").delete().eq("id", draft["id"]).execute()
                        logging.info(f"✅ Đã xóa draft khỏi Supabase. Gmail Draft ID: {gmail_draft_id}")
                        return True
            
            logging.warning(f"⚠️ Không tìm thấy draft với Gmail Draft ID: {gmail_draft_id}")
            return False
            
        except Exception as e:
            logging.error(f"❌ Lỗi xóa draft: {e}")
            return False
    
    def check_draft_exists(self, email_id: str, user_id: str):
        """
        Kiểm tra xem email đã có draft chưa
        
        Args:
            email_id: ID của email gốc
            user_id: ID của user
        
        Returns:
            Bool: True nếu đã tồn tại, False nếu chưa
        """
        try:
            res = self.db.table("email_drafts").select("id").eq("email_id", email_id).eq("user_id", user_id).execute()
            return res.data and len(res.data) > 0
            
        except Exception as e:
            logging.error(f"❌ Lỗi kiểm tra draft: {e}")
            return False
