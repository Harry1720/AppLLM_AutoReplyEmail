from google.oauth2 import id_token
from google.auth.transport import requests
import os, jwt, datetime
from app.domain.entities.user_entity import UserEntity
from fastapi import HTTPException
from app.domain.repositories.user_repository import UserRepository

class LoginWithGoogleUseCase:

    def __init__(self):
        self.repo = UserRepository()

    def execute(self, google_token: str):
        try:
            # KIỂM TRA TOKEN

            CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
            if not CLIENT_ID:
                raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID chưa được cấu hình")
            payload = id_token.verify_oauth2_token
            (
                google_token,
                requests.Request(),
                CLIENT_ID
            )
            email = payload["email"]
            name = payload.get("name", "")
            picture = payload.get("picture", "")

        except ValueError:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
        # KIỂM TRA USER TRONG DB
        user = self.repo.get_by_email(email)
        if not user:
            user = self.repo.create(email, name, picture)
            print("User hiện tại trong DB:", user)


        # TẠO JWT TOKEN CHO FE
        jwt_payload = {
            "user_id": user.id,
            "email": user.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=48)
        }

        token = jwt.encode(jwt_payload, os.getenv("JWT_SECRET"), algorithm="HS256")
    


        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture
            }
        }
