from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from app.infra.services.gmail_service import GmailService 
from typing import Optional, List
from app.api.deps import get_token_dependency
from app.api.user_router import get_current_user_id
from app.core.enums import EmailFolder, EmailStatus
from app.domain.repositories.draft_repository import DraftRepository
from app.domain.entities.draft_entity import DraftEntity # <--- Import Entity
import logging

email_router = APIRouter()

# 1. Đọc danh sách 
@email_router.get("/emails")
async def list_user_emails(
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

# 3. Xóa mail 
@email_router.delete("/emails/{msg_id}")
async def delete_user_email(msg_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    success = service.delete_email(msg_id)
    if success:
        return {"message": "Đã chuyển email vào thùng rác thành công"}
    raise HTTPException(status_code=500, detail="Xóa thất bại (Vui lòng kiểm tra quyền gmail.modify)")

# 4. LẤY CHI TIẾT 1 EMAIL
@email_router.get("/emails/{msg_id}")
async def get_email_detail(msg_id: str, token_data: dict = Depends(get_token_dependency)):
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
async def list_drafts(
    user_id: str = Depends(get_current_user_id)
):
    draft_repo = DraftRepository()
    # Repository trả về List[DraftEntity], FastAPI tự động serialize thành JSON
    drafts = draft_repo.get_all_drafts_by_user(user_id)
    return {"drafts": drafts}

# 9.LẤY DANH SÁCH EMAIL ĐÃ GỬI 
@email_router.get("/drafts/sent-emails")
async def get_sent_email_ids(user_id: str = Depends(get_current_user_id)):
    draft_repo = DraftRepository()
    sent_ids = draft_repo.get_sent_email_ids(user_id)
    return {
        "sent_email_ids": sent_ids,
        "count": len(sent_ids)
    }

# 10. LẤY CHI TIẾT MỘT DRAFT (Đã sửa truy cập Entity)
@email_router.get("/drafts/{draft_id}")
async def get_draft_detail(
    draft_id: str,
    token_data: dict = Depends(get_token_dependency)
):
    # Thử lấy từ Supabase trước
    draft_repo = DraftRepository()
    supabase_draft = draft_repo.get_draft_by_gmail_id(draft_id)
    
    if supabase_draft:
        # === ĐÃ SỬA: Truy cập bằng dấu chấm (Entity Attribute) ===
        return {
            "data": {
                "id": supabase_draft.draft_id,       # Không dùng .get()
                "subject": supabase_draft.subject,
                "to": supabase_draft.recipient,
                "body": supabase_draft.body,
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

# 14. GỬI BẢN NHÁP ĐI 
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
    
    # Lấy draft hiện tại từ Supabase (Trả về Entity)
    current_draft = draft_repo.get_draft_by_gmail_id(draft_id)
    
    if current_draft:
        # === ĐÃ SỬA: Truy cập thuộc tính Object ===
        # Sử dụng 'or ""' để xử lý trường hợp None
        db_subject = current_draft.subject or ""
        db_body = current_draft.body or ""
        db_recipient = current_draft.recipient or ""

        final_subject = subject if subject else db_subject
        final_body = body if body else db_body
        final_recipient = recipient if recipient else db_recipient
        
        # CHỈ UPDATE KHI NỘI DUNG THỰC SỰ KHÁC
        content_changed = (
            final_subject != db_subject or
            final_body != db_body or
            final_recipient != db_recipient
        )
        
        if content_changed:
            
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
async def delete_user_draft(draft_id: str, token_data: dict = Depends(get_token_dependency)):
    service = GmailService(token_data)
    draft_repo = DraftRepository()
    
    gmail_success = service.delete_draft(draft_id)
    
    if not gmail_success:
        raise HTTPException(status_code=500, detail="Xóa bản nháp trên Gmail thất bại")
    
    supabase_success = draft_repo.delete_draft_by_gmail_id(draft_id)
    
    # Success if deleted from at least one place
    if gmail_success or supabase_success:
        return {
            "message": f"Đã xóa bản nháp thành công",
            "gmail_deleted": gmail_success,
            "supabase_deleted": supabase_success
        }
    
    raise HTTPException(status_code=404, detail="Không tìm thấy bản nháp ở cả Gmail và Supabase")