from app.infra.supabase_client import get_supabase
from app.domain.entities.user_entity import UserEntity
from fastapi import HTTPException

class UserRepository:

    def __init__(self):
        self.db = get_supabase()
        try:
            self.db = get_supabase()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase client lỗi: {e}")

    def get_by_email(self, email: str):
        res = self.db.table("users").select("*").eq("email", email).execute()
        if res.data:
            row = res.data[0]
            return UserEntity(
                id=row["id"],
                email=row["email"],
                name=row["name"],
                picture=row.get("picture", "")
            )
        return None

    def create(self, email: str, name: str, picture: str):
        new_user = {
            "email": email,
            "name": name,
            "picture": picture
        }
        res = self.db.table("users").insert(new_user).execute()
        row = res.data[0]

        return UserEntity(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            picture=row.get("picture", "")
        )

