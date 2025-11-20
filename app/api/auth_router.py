from fastapi import APIRouter
from pydantic import BaseModel

from app.use_case.login_with_google import LoginWithGoogleUseCase

router = APIRouter(prefix="/auth", tags=["Auth"])

class GoogleLoginRequest(BaseModel):
    id_token: str

@router.post("/google-login")
def login_google(req: GoogleLoginRequest):
    use_case = LoginWithGoogleUseCase()
    return use_case.execute(req.id_token)
