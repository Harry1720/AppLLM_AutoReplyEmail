# app/use_case/login_with_google.py
import os
import jwt
import datetime
from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow 
from app.domain.repositories.user_repository import UserRepository

# --- DÒNG SỬA LỖI QUAN TRỌNG ---
# Cho phép Google tự động thêm scope openid mà không báo lỗi
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
# -------------------------------

class LoginWithGoogleUseCase:

    def __init__(self):
        self.repo = UserRepository()
        # Cấu hình OAuth lấy từ Google Cloud Console (.env)
        self.client_config = {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    def execute(self, auth_code: str, background_tasks=None):
        try:
            # 1. Thiết lập Flow
            # redirect_uri phải khớp 100% với link bạn dùng trên trình duyệt
            flow = Flow.from_client_config(
                self.client_config,
                scopes=[
                    "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/userinfo.profile",
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/gmail.modify"
                ],
                redirect_uri="http://localhost:3000/auth/callback" 
            )

            # 2. Đổi Code lấy Token
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials

            # 3. Lấy thông tin User
            session = flow.authorized_session()
            user_info = session.get('https://www.googleapis.com/userinfo/v2/me').json()
            
            email = user_info["email"]
            name = user_info.get("name", "")
            picture = user_info.get("picture", "")
            
            # LẤY REFRESH TOKEN
            refresh_token = credentials.refresh_token

        except Exception as e:
            # In lỗi ra terminal để debug nếu có biến
            print("="*30)
            print(f"❌ LỖI GOOGLE TRẢ VỀ: {e}") 
            print("="*30)
            raise HTTPException(status_code=401, detail=f"Xác thực thất bại: {str(e)}")

        # 4. LƯU VÀO DB (Supabase)
        # Logic: Tìm user -> Nếu chưa có thì tạo -> Nếu có rồi thì update token
        user = self.repo.get_by_email(email)
        
        if not user:
            # Tạo user mới
            user = self.repo.create(email, name, picture, refresh_token)
        else:
            # User cũ -> Cập nhật token mới (nếu Google có trả về refresh_token)
            if refresh_token:
                self.repo.update_google_token(user.id, refresh_token)

        # 5. TẠO JWT APP
        jwt_payload = {
            "user_id": user.id,
            "email": user.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=48)
        }
        
        token = jwt.encode(
            jwt_payload,
            os.getenv("JWT_SECRET"),
            algorithm="HS256"
        )

        # 6. TỰ ĐỘNG SYNC EMAIL SAU KHI ĐĂNG NHẬP
        # Lấy refresh_token từ DB (vì Google chỉ trả refresh_token lần đầu)
        if background_tasks:
            # Lấy refresh_token từ user object (đã có trong DB)
            stored_refresh_token = user.google_refresh_token if hasattr(user, 'google_refresh_token') else None
            
            # Ưu tiên refresh_token mới từ Google, không có thì dùng token đã lưu
            final_refresh_token = refresh_token or stored_refresh_token
            
            if final_refresh_token:
                token_data = {
                    'token': credentials.token,
                    'refresh_token': final_refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                
                def run_sync_after_login():
                    try:
                        print(f"🔄 Tự động sync email sau đăng nhập cho user {user.id}...")
                        from app.infra.ai.vectorizer import EmailVectorizer
                        vec = EmailVectorizer(user.id, token_data)
                        result = vec.sync_user_emails()
                        print(f"✅ Kết quả auto-sync: {result}")
                    except Exception as e:
                        print(f"❌ Lỗi auto-sync sau login: {e}")
                
                background_tasks.add_task(run_sync_after_login)
                print(f"📧 Đã thêm task tự động sync email cho user {user.id}")
            else:
                print(f"⚠️ Không tìm thấy refresh_token cho user {user.id}, bỏ qua auto-sync")

        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture
            }
        }