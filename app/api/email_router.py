from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from app.infra.services.gmail_service import GmailService 
from typing import Optional, List
from app.api.deps import get_token_dependency
from app.core.enums import EmailFolder, EmailStatus
email_router = APIRouter()
from typing import Optional

# 1. API Đọc danh sách (Read)
@email_router.get("/emails")
def list_user_emails(
    limit: int = Query(10, description="Số lượng email muốn lấy"),
    page_token: Optional[str] = Query(None, description="Mã token của trang tiếp theo"),
    folder: EmailFolder = Query(EmailFolder.INBOX, description="Chọn thư mục (INBOX, SENT, ARCHIVE...)"),
    status: EmailStatus = Query(EmailStatus.ALL, description="Lọc trạng thái (UNREAD, STARRED...)"),
    token_data: dict = Depends(get_token_dependency)
): 
    service = GmailService(token_data)
    
    # Gọi service truyền các tham số lọc
    # folder.value và status.value dùng để lấy chuỗi text thực tế (vd: "INBOX")
    return service.get_emails(
        max_results=limit, 
        page_token=page_token,
        folder=folder.value,
        status=status.value
    )

# 2. API Gửi mail (Create)
# @email_router.post("/emails/send")
# def send_user_email(to: str, subject: str, body: str, token_data: dict = Depends(get_token_dependency)):
#     service = GmailService(token_data)
#     result = service.send_email(to, subject, body)
#     if result:
#         return {"message": "Gửi thành công", "id": result['id']}
#     raise HTTPException(status_code=500, detail="Gửi thất bại")

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

# 5. API Gửi mail kèm tệp đính kèm (Create with Attachments)
@email_router.post("/emails/send")
async def send_user_email(
    to: str = Form(..., description="Email người nhận"),
    subject: str = Form(..., description="Tiêu đề"),
    body: str = Form(..., description="Nội dung"),
    files: Optional[List[UploadFile]] = File(None, description="Chọn file đính kèm (Tùy chọn)"),
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    
    # Xử lý file upload
    attachment_list = []
    if files:
        for file in files:
            content = await file.read() # Đọc file thành bytes
            attachment_list.append({
                "filename": file.filename,
                "content": content,
                "content_type": file.content_type
            })

    # Gọi service gửi
    result = service.send_email(to, subject, body, attachments=attachment_list)
    
    if result:
        return {"message": "Gửi thành công", "id": result['id']}
    
    raise HTTPException(status_code=500, detail="Gửi thất bại")

# 5. API LƯU TRỮ (Archive)
@email_router.post("/emails/{msg_id}/archive")
def archive_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.archive_email(msg_id)
    if success:
        return {"message": "Đã lưu trữ email (Archived)"}
    raise HTTPException(status_code=500, detail="Lưu trữ thất bại")

# 6. API GẮN SAO (Star)
@email_router.post("/emails/{msg_id}/star")
def star_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.star_email(msg_id)
    if success:
        return {"message": "Đã gắn sao thành công ⭐"}
    raise HTTPException(status_code=500, detail="Gắn sao thất bại")

# 7. API BỎ SAO (Unstar)
@email_router.delete("/emails/{msg_id}/star")
def unstar_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.unstar_email(msg_id)
    if success:
        return {"message": "Đã bỏ sao thành công"}
    raise HTTPException(status_code=500, detail="Bỏ sao thất bại")

# --- API LẤY DANH SÁCH DRAFTS ---
@email_router.get("/drafts")
def list_drafts(
    limit: int = Query(10, description="Số lượng draft muốn lấy"),
    page_token: Optional[str] = Query(None),
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    
    # Gọi hàm mới viết
    return service.get_drafts(max_results=limit, page_token=page_token)

# app/api/email_router.py

# ... (Các API cũ giữ nguyên) ...

# --- API ĐÁNH DẤU ĐÃ ĐỌC ---
@email_router.post("/emails/{msg_id}/read")
def mark_email_as_read(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.mark_as_read(msg_id)
    if success:
        return {"message": "Đã đánh dấu đã đọc"}
    raise HTTPException(status_code=500, detail="Thất bại")

# --- API ĐÁNH DẤU CHƯA ĐỌC ---
@email_router.post("/emails/{msg_id}/unread")
def mark_email_as_unread(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.mark_as_unread(msg_id)
    if success:
        return {"message": "Đã đánh dấu chưa đọc"}
    raise HTTPException(status_code=500, detail="Thất bại")


# --- API TRẢ LỜI EMAIL ---
@email_router.post("/emails/{msg_id}/reply")
async def reply_user_email(
    msg_id: str,
    body: str = Form(..., description="Nội dung trả lời"),
    # 👇 SỬA DÒNG NÀY: Thêm Optional và File(None)
    files: Optional[List[UploadFile]] = File(None, description="File đính kèm (Tùy chọn)"), 
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    
    # Xử lý file (Thêm kiểm tra if files)
    attachment_list = []
    
    # 👇 QUAN TRỌNG: Kiểm tra xem user có gửi file không rồi mới lặp
    if files: 
        for file in files:
            # Kiểm tra file rỗng (Swagger đôi khi gửi file rỗng nếu không chọn gì)
            if file.filename: 
                content = await file.read()
                attachment_list.append({
                    "filename": file.filename,
                    "content": content,
                    "content_type": file.content_type
                })

    result = service.reply_email(msg_id, body, attachments=attachment_list)
    
    if result:
        return {"message": "Đã gửi câu trả lời thành công", "id": result['id']}
    
    raise HTTPException(status_code=500, detail="Trả lời thất bại")


# --- API CẬP NHẬT BẢN NHÁP ---
@email_router.put("/drafts/{draft_id}")
def update_existing_draft(
    draft_id: str,
    to: str = Form(..., description="Email người nhận"),
    subject: str = Form(..., description="Tiêu đề mới"),
    body: str = Form(..., description="Nội dung mới"),
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    
    # Gọi hàm update
    result = service.update_draft(draft_id, to, subject, body)
    
    if result:
        return {"message": "Cập nhật bản nháp thành công", "draft": result}
    
    raise HTTPException(status_code=500, detail="Cập nhật thất bại")


# --- API GỬI BẢN NHÁP ĐI ---
@email_router.post("/drafts/{draft_id}/send")
def send_existing_draft(draft_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    
    result = service.send_draft(draft_id)
    
    if result:
        return {"message": "Bản nháp đã được gửi đi thành công", "id": result['id']}
    
    raise HTTPException(status_code=500, detail="Không gửi được bản nháp (Kiểm tra lại ID)")


# --- API XÓA BẢN NHÁP ---
@email_router.delete("/drafts/{draft_id}")
def delete_user_draft(draft_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    
    success = service.delete_draft(draft_id)
    
    if success:
        return {"message": "Đã xóa bản nháp thành công"}
    
    raise HTTPException(status_code=500, detail="Xóa bản nháp thất bại")