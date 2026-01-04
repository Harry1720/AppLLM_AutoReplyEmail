from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.api.deps import get_token_dependency
from app.api.user_router import get_current_user_id
from app.infra.supabase_client import get_supabase
import logging

# Khởi tạo router
ai_router = APIRouter()

# MODELS 
class GenerateRequest(BaseModel):
    msg_id: str # ID của email cần trả lời


# ĐỒNG BỘ EMAIL CŨ CHẠY NGẦM
@ai_router.post("/ai/sync")
async def sync_data(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    def run_sync_process():
        try:
            
            # Import bên trong để tránh lỗi vòng lặp
            from app.infra.ai.vectorizer import EmailVectorizer
            
            vec = EmailVectorizer(user_id, token_data)
            result = vec.sync_user_emails()
            print(f"Kết quả Sync: {result}")
        except Exception as e:
            print(f"Lỗi Sync: {e}")

    # Thêm task vào hàng đợi chạy ngầm
    background_tasks.add_task(run_sync_process)
    
    return {
        "status": "success",
        "message": "Hệ thống đang đọc email cũ của bạn để học. Quá trình này sẽ chạy ngầm."
    }


# GỢI Ý TRẢ LỜI  
@ai_router.post("/ai/generate")
async def generate_reply(
    req: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    try:
        # Import workflow xử lý AI
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
        print(f"Đang gọi Ollama xử lý email {req.msg_id}...")
        result = app.invoke(initial_state)
        
        if result.get("error"):
             raise HTTPException(status_code=500, detail=result["error"])

        # Trả về kết quả bao gồm cả draft_id
        draft_data = result.get("draft_reply", {})
        return {
            "message": "Đã tạo bản nháp thành công", 
            "draft": draft_data,
            "draft_id": draft_data.get("draft_id") 
        }
        
    except Exception as e:
        print(f"Lỗi AI Router: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# KIỂM TRA TRẠNG THÁI SYNC 
@ai_router.get("/ai/sync-status")
async def check_sync_status(user_id: str = Depends(get_current_user_id)):
    try:
        db = get_supabase()
        
        # Đếm số lượng document của user trong bảng documents
        response = db.table("documents").select("id", count="exact").eq("metadata->>user_id", user_id).execute()
       
        # Lấy số lượng (xử lý an toàn nếu response không có count)
        doc_count = response.count if hasattr(response, 'count') else 0
        
        return {
            "synced": doc_count > 0,
            "document_count": doc_count,
            "message": "Đã có ngữ cảnh" if doc_count > 0 else "Chưa có ngữ cảnh"
        }
        
    except Exception as e:
        logging.error(f"Lỗi check sync status: {e}")
        return {
            "synced": False,
            "document_count": 0,
            "message": "Lỗi kiểm tra trạng thái"
        }