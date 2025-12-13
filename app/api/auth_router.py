# app/api/auth_router.py
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.use_case.login_with_google import LoginWithGoogleUseCase

router = APIRouter(prefix="/auth", tags=["Auth"])

# Đổi tên trường input cho đúng bản chất
class GoogleLoginRequest(BaseModel):
    code: str # Frontend gửi "Authorization Code"

@router.post("/google-login")
def login_google(req: GoogleLoginRequest, background_tasks: BackgroundTasks):
    use_case = LoginWithGoogleUseCase()
    # Truyền code vào execute, kèm background_tasks để tự động sync
    return use_case.execute(req.code, background_tasks)