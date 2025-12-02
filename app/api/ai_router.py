from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.api.deps import get_token_dependency
from app.api.user_router import get_current_user_id

ai_router = APIRouter()

# Model dữ liệu đầu vào
class GenerateRequest(BaseModel):
    msg_id: str # ID của email cần trả lời

# --- API 1: ĐỒNG BỘ EMAIL CŨ (Để AI học) ---
# Chạy ngầm (Background) vì tốn thời gian
@ai_router.post("/ai/sync")
async def sync_data(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    def run_sync_process():
        try:
            print(f"🔄 Bắt đầu đồng bộ cho user {user_id}...")
            # Import bên trong để tránh lỗi vòng lặp
            from app.infra.ai.vectorizer import EmailVectorizer
            
            vec = EmailVectorizer(user_id, token_data)
            result = vec.sync_user_emails()
            print(f"✅ Kết quả Sync: {result}")
        except Exception as e:
            print(f"❌ Lỗi Sync: {e}")
    
    # Đẩy vào chạy ngầm
    background_tasks.add_task(run_sync_process)
    
    return {"message": "Hệ thống đang đọc email cũ của bạn để học. Vui lòng đợi vài phút."}

# --- API 2: GỢI Ý TRẢ LỜI (Single Email) ---
# Dùng Ollama chạy local có thể mất 5-10s, Frontend cần hiện Loading
@ai_router.post("/ai/generate")
async def generate_reply(
    req: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    try:
        from app.infra.ai.reasoning import create_single_email_workflow, GraphState
        
        # Khởi tạo Workflow
        app = create_single_email_workflow(user_id, token_data)
        
        # Tạo trạng thái ban đầu
        initial_state = GraphState(
            user_id=user_id,
            target_email_id=req.msg_id, # ID email user chọn
            current_email={},
            context_emails=[],
            draft_reply={},
            error=""
        )
        
        # Chạy quy trình
        print(f"🤖 Đang gọi Ollama xử lý email {req.msg_id}...")
        result = app.invoke(initial_state)
        
        if result.get("error"):
             raise HTTPException(status_code=500, detail=result["error"])

        # Trả về kết quả bao gồm cả draft_id
        draft_data = result.get("draft_reply", {})
        return {
            "message": "Đã tạo bản nháp thành công", 
            "draft": draft_data,
            "draft_id": draft_data.get("draft_id")  # Thêm draft_id vào response
        }
        
    except Exception as e:
        print(f"❌ Lỗi AI Router: {e}")
        raise HTTPException(status_code=500, detail=str(e))