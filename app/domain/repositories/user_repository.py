# app/domain/repositories/user_repository.py
from app.infra.supabase_client import get_supabase
from app.domain.entities.user_entity import UserEntity

class UserRepository:
    def __init__(self):
        self.db = get_supabase()

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
            print(f"⚠️ Lỗi get_by_email (không ảnh hưởng nếu là user mới): {e}")
            return None

    def create(self, email: str, name: str, picture: str, refresh_token: str = None):
        # Dùng UPSERT: Nếu email trùng -> Tự động Update, Không báo lỗi nữa
        new_user = {
            "email": email,
            "name": name,
            "picture": picture,
            "google_refresh_token": refresh_token
        }
        
        # on_conflict="email" nghĩa là: Nếu trùng email thì update dòng đó
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

    def update_google_token(self, user_id: str, refresh_token: str):
        self.db.table("users").update({
            "google_refresh_token": refresh_token
        }).eq("id", user_id).execute()