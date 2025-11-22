from fastapi import APIRouter, Depends, HTTPException
from infra.services.gmail_service import GmailService
# Giả sử bạn có hàm lấy current_user kèm token từ DB
# from api.deps import get_current_user_token 

email_router = APIRouter()

# 1. API Đọc danh sách (Read)
@email_router.get("/emails")
def list_user_emails(token_data: dict = Depends(get_token_dependency)): 
    # token_data cần chứa access_token, refresh_token, etc.
    service = GmailService(token_data)
    emails = service.get_emails(max_results=5)
    return {"data": emails}

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
    service = GmailService(token_data)
    success = service.delete_email(msg_id)
    if success:
        return {"message": "Đã xóa email"}
    raise HTTPException(status_code=500, detail="Xóa thất bại")