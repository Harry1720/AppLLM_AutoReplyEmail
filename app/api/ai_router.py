from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.api.deps import get_token_dependency
from app.api.user_router import get_current_user_id
from app.use_case.SyncEmailsUseCase import SyncEmailsUseCase
from app.use_case.GenerateReplyUseCase import GenerateReplyUseCase
from app.use_case.CheckSyncStatusUseCase import CheckAndAutoSyncUseCase

ai_router = APIRouter()

class GenerateRequest(BaseModel):
    msg_id: str 

#  1. API ĐỒNG BỘ (CHẠY NGẦM) 
@ai_router.post("/ai/sync")
async def sync_data(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    # Hàm wrapper để chạy trong background
    def run_sync_process():
        try:
            use_case = SyncEmailsUseCase(user_id, token_data)
            use_case.execute()
        except Exception as e:
            print(f"Lỗi Background Sync: {e}")

    background_tasks.add_task(run_sync_process)
    
    return {
        "status": "success",
        "message": "Hệ thống đang đọc email cũ của bạn để học (Background Task)."
    }

# 2. API GỢI Ý TRẢ LỜI 
@ai_router.post("/ai/generate")
async def generate_reply(
    req: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    try:
        # Gọi UseCase
        use_case = GenerateReplyUseCase(user_id, token_data)
        result = use_case.execute(req.msg_id)
        return result
        
    except Exception as e:
        print(f"Lỗi Generate Reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 3. API KIỂM TRA & AUTO SYNC 
@ai_router.get("/ai/sync-status")
async def check_sync_status(
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    try:
        # Gọi UseCase
        use_case = CheckAndAutoSyncUseCase(user_id, token_data)
        result = use_case.execute()
        return result
        
    except Exception as e:
        print(f"Lỗi Check Status: {e}")
        raise HTTPException(status_code=500, detail=str(e))