# app/api/deps.py
import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from app.domain.repositories.user_repository import UserRepository
from dotenv import load_dotenv

# 1. Load biến môi trường ngay lập tức để tránh lỗi None
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

# Debug: Kiểm tra xem Secret có nạp được không
if not JWT_SECRET:
    print("❌ LỖI: Không tìm thấy JWT_SECRET trong file .env!")
else:
    print(f"✅ DEPS: Đã load JWT_SECRET (bắt đầu bằng: {JWT_SECRET[:5]}...)")

# 2. Khởi tạo scheme Bearer
security = HTTPBearer()

def get_token_dependency(token_auth: HTTPAuthorizationCredentials = Depends(security)):
    """
    Hàm này lấy Token từ Header: "Authorization: Bearer <token>"
    """
    # Lấy chuỗi token
    token = token_auth.credentials
    
    # --- DEBUG: In token nhận được ra terminal để soi ---
    print("="*30)
    print(f"👉 TOKEN NHẬN TỪ SWAGGER: {token}")
    print("="*30)
    # ---------------------------------------------------

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 3. Giải mã JWT App
        # Quan trọng: algorithms phải là một list [...]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        
        email: str = payload.get("email")
        
        print(f"✅ Giải mã thành công. User Email: {email}")

        if email is None:
            print("❌ Lỗi: Payload không chứa email")
            raise credentials_exception
            
    except jwt.ExpiredSignatureError:
        print("❌ LỖI: Token đã hết hạn (Expired)")
        raise credentials_exception
    except jwt.InvalidTokenError as e:
        print(f"❌ LỖI: Token không hợp lệ (Invalid): {str(e)}")
        # Gợi ý lỗi thường gặp
        if "Signature verification failed" in str(e):
             print("💡 Gợi ý: Kiểm tra lại JWT_SECRET trong .env xem có trùng khớp với file tạo token không.")
        raise credentials_exception

    # 4. Tìm User trong DB
    try:
        repo = UserRepository()
        user = repo.get_by_email(email)

        if not user:
            print(f"❌ Lỗi: Không tìm thấy user {email} trong Database")
            raise HTTPException(status_code=400, detail="User không tồn tại")

        if not user.google_refresh_token:
            print(f"❌ Lỗi: User {email} chưa có Google Refresh Token")
            raise HTTPException(
                status_code=400, 
                detail="User chưa kết nối tài khoản Google (Thiếu Refresh Token)"
            )
            
        return {
            "access_token": None,
            "refresh_token": user.google_refresh_token,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET")
        }
        
    except Exception as e:
        print(f"❌ Lỗi Database/Logic khác: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống khi xác thực")