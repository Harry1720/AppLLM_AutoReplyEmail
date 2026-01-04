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
        print(f"Đang gọi Groq xử lý email {req.msg_id}...")
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


# KIỂM TRA TRẠNG THÁI SYNC + TỰ ĐỘNG SYNC NẾU THIẾU
@ai_router.get("/ai/sync-status")
async def check_sync_status(
    user_id: str = Depends(get_current_user_id),
    token_data: dict = Depends(get_token_dependency)
):
    try:
        db = get_supabase()
        
        # Đếm số lượng document của user trong bảng documents
        response = db.table("documents").select("id", count="exact").eq("metadata->>user_id", user_id).execute()
       
        # Lấy số lượng (xử lý an toàn nếu response không có count)
        doc_count = response.count if hasattr(response, 'count') else 0
        
        # KIỂM TRA XEM CÓ EMAIL SENT MỚI CHƯA ĐƯỢC VECTOR HÓA KHÔNG
        from app.infra.ai.vectorizer import EmailVectorizer
        from app.infra.services.gmail_service import GmailService
        
        try:
            # Lấy danh sách email sent từ Gmail
            gmail_service = GmailService(token_data)
            result = gmail_service.get_emails(max_results=50, folder="SENT")
            sent_emails = result.get('emails', [])
            
            if sent_emails:
                # Lấy danh sách email đã có trong database
                vec = EmailVectorizer(user_id, token_data)
                existing_email_ids = vec._get_existing_email_ids()
                
                # Tính số email mới chưa vector hóa
                new_email_ids = [e['id'] for e in sent_emails if e['id'] not in existing_email_ids]
                pending_count = len(new_email_ids)
                
                # NẾU CÓ EMAIL MỚI → TỰ ĐỘNG SYNC NGAY
                if pending_count > 0:
                    logging.info(f"🔄 Phát hiện {pending_count} email mới chưa vector hóa, bắt đầu sync...")
                    sync_result = vec.sync_user_emails()
                    
                    # Đếm lại sau khi sync
                    response_after = db.table("documents").select("id", count="exact").eq("metadata->>user_id", user_id).execute()
                    doc_count = response_after.count if hasattr(response_after, 'count') else 0
                    
                    return {
                        "synced": True,
                        "document_count": doc_count,
                        "pending_emails": 0,
                        "just_synced": sync_result.get("synced_count", 0),
                        "message": f"✓ Đã đồng bộ {sync_result.get('synced_count', 0)} email mới"
                    }
                else:
                    return {
                        "synced": doc_count > 0,
                        "document_count": doc_count,
                        "pending_emails": 0,
                        "message": "✓ Tất cả email đã được đồng bộ"
                    }
            else:
                return {
                    "synced": doc_count > 0,
                    "document_count": doc_count,
                    "pending_emails": 0,
                    "message": "Không có email sent"
                }
                
        except Exception as sync_error:
            logging.warning(f"Không thể kiểm tra/sync tự động: {sync_error}")
            # Fallback về check cơ bản
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