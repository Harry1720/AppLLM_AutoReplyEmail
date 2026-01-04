from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
import jwt
import os
from app.api.deps import get_token_dependency, security 
from app.domain.repositories.user_repository import UserRepository

user_router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET")

# Model dữ liệu để hứng Body khi Update
class UpdateProfileRequest(BaseModel):
    name: str
    picture: str = None

# Lấy User ID từ Token 
def get_current_user_id(token_auth=Depends(security)):
    token = token_auth.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("user_id") 
    except:
        raise HTTPException(status_code=401, detail="Token lỗi")

# XEM PROFILE 
@user_router.get("/users/me")
def get_my_profile(user_id: str = Depends(get_current_user_id)):
    repo = UserRepository()
    user = repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")
    
    # Trả về thông tin (Che token đi cho bảo mật)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "picture": user.picture
    }

# CẬP NHẬT PROFILE 
@user_router.put("/users/me")
def update_my_profile(
    req: UpdateProfileRequest, 
    user_id: str = Depends(get_current_user_id)
):
    repo = UserRepository()
    success = repo.update_profile(user_id, req.name, req.picture)
    
    if success:
        return {"message": "Cập nhật thành công", "name": req.name}
    raise HTTPException(status_code=500, detail="Cập nhật thất bại")

# XÓA TÀI KHOẢN 
@user_router.delete("/users/me")
def delete_my_account(user_id: str = Depends(get_current_user_id)):
    repo = UserRepository()
    success = repo.delete_user(user_id)
    
    if success:
        return {"message": "Tài khoản đã bị xóa vĩnh viễn. Bye bye!"}
    raise HTTPException(status_code=500, detail="Xóa thất bại")