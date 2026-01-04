from app.infra.supabase_client import get_supabase
from app.domain.entities.user_entity import UserEntity
from datetime import datetime, timedelta, timezone

# Helper function để lấy giờ Việt Nam
def get_vietnam_time():
    """Trả về thời gian hiện tại theo múi giờ Việt Nam (UTC+7)"""
    return datetime.now(timezone.utc) + timedelta(hours=7)

class UserRepository:
    def __init__(self):
        self.db = get_supabase()

    # LẤY USER THEO EMAIL 
    def get_by_email(self, email: str):
        try:
            res = self.db.table("users").select("*").eq("email", email).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                return UserEntity(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"],
                    picture=row.get("picture", ""),
                    google_refresh_token=row.get("google_refresh_token")
                )
            return None
        except Exception as e:
            print(f"Lỗi get_by_email: {e}")
            return None

    # TẠO HOẶC CẬP NHẬT USER 
    def create(self, email: str, name: str, picture: str, refresh_token: str = None):
        new_user = {
            "email": email,
            "name": name,
            "picture": picture,
            "google_refresh_token": refresh_token,
            "created_at": get_vietnam_time().isoformat()  # Set giờ Việt Nam
        }
        
        # Dùng UPSERT để tránh lỗi trùng email
        res = self.db.table("users").upsert(new_user, on_conflict="email").execute()
        
        if res.data:
            row = res.data[0]
            return UserEntity(
                id=row["id"],
                email=row["email"],
                name=row["name"],
                picture=row["picture"],
                google_refresh_token=refresh_token
            )
        raise Exception("Không thể tạo hoặc cập nhật User")

    # CẬP NHẬT TOKEN (Dùng khi refresh) ---
    def update_google_token(self, user_id: str, refresh_token: str):
        self.db.table("users").update({
            "google_refresh_token": refresh_token
        }).eq("id", user_id).execute()

    # LẤY USER THEO ID (Dùng cho Profile) ---
    def get_by_id(self, user_id: str):
        try:
            res = self.db.table("users").select("*").eq("id", user_id).execute()
            if res.data:
                row = res.data[0]
                return UserEntity(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"],
                    picture=row.get("picture", ""),
                    google_refresh_token=row.get("google_refresh_token")
                )
            return None
        except Exception as e:
            print(f"Lỗi get_by_id: {e}")
            return None

    # CẬP NHẬT PROFILE 
    def update_profile(self, user_id: str, name: str, picture: str = None):
        data = {"name": name}
        if picture:
            data["picture"] = picture
            
        try:
            self.db.table("users").update(data).eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Lỗi update_profile: {e}")
            return False

    # XÓA USER 
    def delete_user(self, user_id: str):
        try:
            
            # 1. Xóa tất cả documents của user
            self.db.table("documents").delete().eq("user_id", user_id).execute()
            print(f"Đã xóa documents của user {user_id}")
            
            # 2. Xóa tất cả email_drafts của user
            self.db.table("email_drafts").delete().eq("user_id", user_id).execute()
            print(f"Đã xóa email_drafts của user {user_id}")
            
            # 3. Cuối cùng mới xóa user
            self.db.table("users").delete().eq("id", user_id).execute()
            print(f"Đã xóa user {user_id}")
            
            return True
        except Exception as e:
            print(f"Lỗi delete_user: {e}")
            return False