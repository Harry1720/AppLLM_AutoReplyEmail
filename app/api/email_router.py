from fastapi import APIRouter, Depends, HTTPException, Query
from app.infra.services.gmail_service import GmailService 
from typing import Optional
from app.api.deps import get_token_dependency
email_router = APIRouter()
from typing import Optional

# 1. API Đọc danh sách (Read)
@email_router.get("/emails")
def list_user_emails(
    limit: int = Query(10, description="Số lượng mail"),
    page_token: Optional[str] = Query(None, description="Token trang tiếp theo"),
    token_data: dict = Depends(get_token_dependency)
): 
    service = GmailService(token_data)
    
    # Gọi service
    result = service.get_emails(max_results=limit, page_token=page_token)
    
    # Kết quả trả về sẽ là:
    # {
    #   "emails": [...],
    #   "next_page_token": "..."
    # }
    return result

# 2. API Gửi mail (Create)
@email_router.post("/emails/send")
def send_user_email(to: str, subject: str, body: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    result = service.send_email(to, subject, body)
    if result:
        return {"message": "Gửi thành công", "id": result['id']}
    raise HTTPException(status_code=500, detail="Gửi thất bại")

# 3. API Xóa mail (Delete)
@email_router.delete("/emails/{msg_id}")
def delete_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    # 1. Khởi tạo Service bằng token lấy được
    service = GmailService(token_data)
    
    # 2. Gọi hàm xóa bên Service
    success = service.delete_email(msg_id)
    
    # 3. Trả kết quả về cho người dùng
    if success:
        return {"message": "Đã chuyển email vào thùng rác thành công"}
    
    raise HTTPException(status_code=500, detail="Xóa thất bại (Vui lòng kiểm tra quyền gmail.modify)")

# 4. API LẤY CHI TIẾT 1 EMAIL
@email_router.get("/emails/{msg_id}")
def get_email_detail(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    
    email_detail = service.get_email_detail(msg_id)
    
    if email_detail:
        return {"data": email_detail}
    
    raise HTTPException(status_code=404, detail="Không tìm thấy email hoặc lỗi khi đọc")