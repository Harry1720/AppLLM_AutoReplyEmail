from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from app.infra.services.gmail_service import GmailService 
from typing import Optional, List
from app.api.deps import get_token_dependency
from app.api.user_router import get_current_user_id
from app.core.enums import EmailFolder, EmailStatus
from app.domain.repositories.draft_repository import DraftRepository
import logging

email_router = APIRouter()

# 1. Đọc danh sách 
@email_router.get("/emails")
def list_user_emails(
    limit: int = Query(10, description="Số lượng email muốn lấy"),
    page_token: Optional[str] = Query(None, description="Mã token của trang tiếp theo"),
    folder: EmailFolder = Query(EmailFolder.INBOX, description="Chọn thư mục (INBOX, SENT, ARCHIVE...)"),
    status: EmailStatus = Query(EmailStatus.ALL, description="Lọc trạng thái (UNREAD, STARRED...)"),
    token_data: dict = Depends(get_token_dependency)
): 
    service = GmailService(token_data)
    
    return service.get_emails(
        max_results=limit, 
        page_token=page_token,
        folder=folder.value,
        status=status.value
    )

# 2. Gửi mail 
@email_router.post("/emails/send")
def send_user_email(to: str, subject: str, body: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    result = service.send_email(to, subject, body)
    if result:
        return {"message": "Gửi thành công", "id": result['id']}
    raise HTTPException(status_code=500, detail="Gửi thất bại")

# 3. Xóa mail 
@email_router.delete("/emails/{msg_id}")
def delete_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.delete_email(msg_id)
    if success:
        return {"message": "Đã chuyển email vào thùng rác thành công"}
    raise HTTPException(status_code=500, detail="Xóa thất bại (Vui lòng kiểm tra quyền gmail.modify)")

# 4. LẤY CHI TIẾT 1 EMAIL
@email_router.get("/emails/{msg_id}")
def get_email_detail(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    
    email_detail = service.get_email_detail(msg_id)
    
    if email_detail:
        return {"data": email_detail}
    
    raise HTTPException(status_code=404, detail="Không tìm thấy email hoặc lỗi khi đọc")

# 5. Gửi mail kèm tệp đính kèm 
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

# 5. LƯU TRỮ (Archive)
@email_router.post("/emails/{msg_id}/archive")
def archive_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.archive_email(msg_id)
    if success:
        return {"message": "Đã lưu trữ email (Archived)"}
    raise HTTPException(status_code=500, detail="Lưu trữ thất bại")

# 6. GẮN SAO (Star)
@email_router.post("/emails/{msg_id}/star")
def star_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.star_email(msg_id)
    if success:
        return {"message": "Đã gắn sao thành công ⭐"}
    raise HTTPException(status_code=500, detail="Gắn sao thất bại")

# 7. BỎ SAO (Unstar)
@email_router.delete("/emails/{msg_id}/star")
def unstar_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.unstar_email(msg_id)
    if success:
        return {"message": "Đã bỏ sao thành công"}
    raise HTTPException(status_code=500, detail="Bỏ sao thất bại")

# 8. LẤY DANH SÁCH DRAFTS
@email_router.get("/drafts")
def list_drafts(
    user_id: str = Depends(get_current_user_id)
):
    draft_repo = DraftRepository()
    drafts = draft_repo.get_all_drafts_by_user(user_id)
    return {"drafts": drafts}

# 9.LẤY DANH SÁCH EMAIL ĐÃ GỬI 
@email_router.get("/drafts/sent-emails")
def get_sent_email_ids(user_id: str = Depends(get_current_user_id)):
    draft_repo = DraftRepository()
    sent_ids = draft_repo.get_sent_email_ids(user_id)
    return {
        "sent_email_ids": sent_ids,
        "count": len(sent_ids)
    }

# 10. LẤY CHI TIẾT MỘT DRAFT 
@email_router.get("/drafts/{draft_id}")
def get_draft_detail(
    draft_id: str,
    token_data: dict = Depends(get_token_dependency)
):
    # Thử lấy từ Supabase trước
    draft_repo = DraftRepository()
    supabase_draft = draft_repo.get_draft_by_gmail_id(draft_id)
    
    if supabase_draft:
        # Trả về draft từ Supabase với format giống Gmail
        return {
            "data": {
                "id": supabase_draft.get("draft_id"),
                "subject": supabase_draft.get("subject"),
                "to": supabase_draft.get("recipient"),
                "body": supabase_draft.get("body"),
            }
        }
    
    # Nếu không có trong Supabase, thử lấy từ Gmail
    service = GmailService(token_data)
    draft_detail = service.get_draft_detail(draft_id)

    if draft_detail:
        return {"data": draft_detail}
    raise HTTPException(status_code=404, detail="Không tìm thấy bản nháp hoặc lỗi khi đọc")

# 11. ĐÁNH DẤU ĐÃ ĐỌC 
@email_router.post("/emails/{msg_id}/read")
def mark_email_as_read(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.mark_as_read(msg_id)
    if success:
        return {"message": "Đã đánh dấu đã đọc"}
    raise HTTPException(status_code=500, detail="Thất bại")

# 12. ĐÁNH DẤU CHƯA ĐỌC ---
@email_router.post("/emails/{msg_id}/unread")
def mark_email_as_unread(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.mark_as_unread(msg_id)
    if success:
        return {"message": "Đã đánh dấu chưa đọc"}
    raise HTTPException(status_code=500, detail="Thất bại")

# 13. TRẢ LỜI EMAIL 
@email_router.post("/emails/{msg_id}/reply")
async def reply_user_email(
    msg_id: str,
    body: str = Form(..., description="Nội dung trả lời"),
    files: Optional[List[UploadFile]] = File(None, description="File đính kèm (Tùy chọn)"), 
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    
    # Xử lý file (Thêm kiểm tra if files)
    attachment_list = []
    
    # Kiểm tra xem user có gửi file không rồi mới lặp
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

# 14. API CẬP NHẬT BẢN NHÁP 
@email_router.put("/drafts/{draft_id}")
def update_existing_draft(
    draft_id: str,
    to: str = Form(..., description="Email người nhận"),
    subject: str = Form(..., description="Tiêu đề mới"),
    body: str = Form(..., description="Nội dung mới"),
    token_data: dict = Depends(get_token_dependency)
):
    service = GmailService(token_data)
    result = service.update_draft(draft_id, to, subject, body)
    
    if result:
        return {"message": "Cập nhật bản nháp thành công", "draft": result}
    
    raise HTTPException(status_code=500, detail="Cập nhật thất bại")

# 14. GỬI BẢN NHÁP ĐI ---
@email_router.post("/drafts/{draft_id}/send")
async def send_existing_draft(
    draft_id: str,
    subject: str = Form(None, description="Tiêu đề email (tuỳ chọn)"),
    body: str = Form(None, description="Nội dung email (tuỳ chọn)"),
    recipient: str = Form(None, description="Email người nhận (tuỳ chọn)"),
    token_data: dict = Depends(get_token_dependency)
):
   
    service = GmailService(token_data)
    draft_repo = DraftRepository()
    
    # Lấy draft hiện tại từ Supabase để so sánh
    current_draft = draft_repo.get_draft_by_gmail_id(draft_id)
    
    if current_draft:
        # Xác định giá trị cuối cùng (ưu tiên giá trị mới nếu có)
        final_subject = subject if subject else current_draft.get("subject", "")
        final_body = body if body else current_draft.get("body", "")
        final_recipient = recipient if recipient else current_draft.get("recipient", "")
        
        # CHỈ UPDATE KHI NỘI DUNG THỰC SỰ KHÁC
        content_changed = (
            final_subject != current_draft.get("subject", "") or
            final_body != current_draft.get("body", "") or
            final_recipient != current_draft.get("recipient", "")
        )
        
        if content_changed:
            logging.info(f"📝 Phát hiện nội dung draft {draft_id} đã được chỉnh sửa, đang cập nhật...")
            
            # 1. Cập nhật nội dung trong Supabase
            draft_repo.update_draft_content(
                draft_id, 
                final_subject, 
                final_body, 
                final_recipient
            )
            
            # 2. Cập nhật nội dung trên Gmail (giữ nguyên threadID)
            gmail_update_result = service.update_draft(
                draft_id,
                final_recipient,
                final_subject,
                final_body
            )
            
            if not gmail_update_result:
                raise HTTPException(status_code=500, detail="Không thể cập nhật bản nháp trên Gmail")
        else:
            logging.info(f"Nội dung draft {draft_id} không thay đổi, bỏ qua cập nhật")
    
    # Gửi draft qua Gmail
    result = service.send_draft(draft_id)
    
    if result:
        draft_repo.update_status(draft_id, "sent")
        
        return {"message": "Bản nháp đã được gửi đi thành công", "id": result['id']}
    
    raise HTTPException(status_code=500, detail="Không gửi được bản nháp (Kiểm tra lại ID)")

# 15. XÓA BẢN NHÁP ---
@email_router.delete("/drafts/{draft_id}")
def delete_user_draft(draft_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    draft_repo = DraftRepository()
    
    gmail_success = service.delete_draft(draft_id)
    
    if not gmail_success:
        raise HTTPException(status_code=500, detail="Xóa bản nháp trên Gmail thất bại")
    
    supabase_success = draft_repo.delete_draft_by_gmail_id(draft_id)
    
    if supabase_success:
        return {
            "message": "Đã xóa bản nháp thành công (cả Gmail và Supabase)",
            "gmail_deleted": True,
            "supabase_deleted": True
        }
    else:
        return {
            "message": "Đã xóa bản nháp trên Gmail (không tìm thấy trong Supabase)",
            "gmail_deleted": True,
            "supabase_deleted": False
        }