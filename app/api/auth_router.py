from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.use_case.login_with_google import LoginWithGoogleUseCase

router = APIRouter(prefix="/auth", tags=["Auth"])

class GoogleLoginRequest(BaseModel):
    code: str 

@router.post("/google-login")
def login_google(req: GoogleLoginRequest, background_tasks: BackgroundTasks):
    use_case = LoginWithGoogleUseCase()
    return use_case.execute(req.code, background_tasks)