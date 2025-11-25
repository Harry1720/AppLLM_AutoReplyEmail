from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders

class GmailService:
    def __init__(self, token_info: dict):
        # Token info là thông tin OAuth nhận được từ FE hoặc DB
        self.creds = Credentials.from_authorized_user_info(token_info)
        self.service = build('gmail', 'v1', credentials=self.creds)


    # --- 1. HÀM LẤY CHI TIẾT (FULL) ---
    def get_email_detail(self, msg_id):
        try:
            # format='full' để lấy toàn bộ nội dung
            msg = self.service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()

            # Lấy Headers
            headers_list = msg['payload']['headers']
            headers = {h['name']: h['value'] for h in headers_list}

            # Lấy Body (Nội dung thư)
            # Gmail chia body thành nhiều phần (parts), cần hàm đệ quy để tìm
            body_html = self._get_body_from_payload(msg['payload'])
            
            return {
                "id": msg['id'],
                "subject": headers.get('Subject', '(No Subject)'),
                "from": headers.get('From', ''),
                "to": headers.get('To', ''),
                "date": headers.get('Date', ''),
                "body": body_html, # Nội dung HTML để hiển thị lên web
                "snippet": msg.get('snippet')
            }

        except Exception as e:
            print(f"❌ Lỗi lấy chi tiết mail: {e}")
            return None

    # --- 2. HÀM PHỤ: GIẢI MÃ BODY GMAIL (Logic phức tạp nhất là ở đây) ---
    def _get_body_from_payload(self, payload):
        """
        Tìm kiếm nội dung text/html hoặc text/plain trong cấu trúc lồng nhau của Gmail
        """
        body = ""
        
        # Trường hợp 1: Nội dung nằm ngay ở ngoài (Email đơn giản)
        if 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        # Trường hợp 2: Nội dung nằm trong parts (Email có đính kèm hoặc HTML phức tạp)
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType')
                
                # Ưu tiên lấy HTML
                if mime_type == 'text/html':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                
                # Nếu không có HTML thì lấy Text thường
                elif mime_type == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                
                # Nếu phần này lại chứa các phần con (Multipart bên trong Multipart) -> Đệ quy
                elif 'parts' in part:
                    found_body = self._get_body_from_payload(part)
                    if found_body:
                        return found_body
        
        return body if body else "(Không thể hiển thị nội dung email này)"

 # --- READ (Đọc danh sách Email - Nâng cấp) ---
    def get_emails(self, max_results=10, page_token=None, folder="INBOX", status="ALL"):
        try:
            print(f"🚀 Lọc Email: Folder={folder}, Status={status}")
            
            # --- LOGIC XÂY DỰNG BỘ LỌC (QUERY) ---
            label_ids = []
            query_parts = []

            # A. Xử lý Thư mục
            if folder == "INBOX":
                label_ids = ['INBOX']
            elif folder == "SENT":
                label_ids = ['SENT']
            elif folder == "TRASH":
                label_ids = ['TRASH']
            elif folder == "ARCHIVE":
                query_parts.append("-in:inbox -in:trash -in:spam")
            
            # B. Xử lý Trạng thái
            if status == "UNREAD":
                query_parts.append("is:unread")
            elif status == "STARRED":
                query_parts.append("is:starred")
            
            final_query = " ".join(query_parts)

            # Gọi API
            results = self.service.users().messages().list(
                userId='me', 
                maxResults=max_results,
                labelIds=label_ids if label_ids else None, 
                q=final_query,
                pageToken=page_token
            ).execute()
            
            messages = results.get('messages', [])
            next_token = results.get('nextPageToken')
            
            email_list = []
            if messages:
                for msg in messages:
                    try:
                        msg_detail = self.service.users().messages().get(
                            userId='me', id=msg['id'], format='metadata'
                        ).execute()
                        
                        headers_list = msg_detail['payload']['headers']
                        headers = {h['name']: h['value'] for h in headers_list}
                        
                        email_list.append({
                            "id": msg['id'],
                            "snippet": msg_detail.get('snippet'),
                            "subject": headers.get('Subject', '(No Subject)'),
                            "from": headers.get('From', ''),
                            "date": headers.get('Date', '')
                        })
                    except Exception:
                        continue 

            return {
                "emails": email_list,
                "next_page_token": next_token
            }

        except Exception as e:
            print(f"❌ Lỗi lọc email: {e}")
            return {"emails": [], "next_page_token": None}

    # --- CREATE (Gửi Email) ---
    def send_email(self, to_email, subject, body_content, attachments=None):
        try:
            # Tạo container (Multipart) thay vì text đơn thuần
            message = MIMEMultipart()
            message['to'] = to_email
            message['subject'] = subject

            # Đính kèm nội dung chữ
            msg_text = MIMEText(body_content, 'html')
            message.attach(msg_text)

            # Xử lý file đính kèm (nếu có)
            if attachments:
                for file_data in attachments:
                    filename = file_data['filename']
                    content = file_data['content'] # Đây là dạng bytes
                    content_type = file_data.get('content_type')

                    # Tự đoán loại file nếu thiếu
                    if not content_type:
                        content_type, _ = mimetypes.guess_type(filename)
                    
                    if content_type is None:
                        content_type = 'application/octet-stream'

                    main_type, sub_type = content_type.split('/', 1)

                    if main_type == 'image':
                        # Xử lý ảnh
                        part = MIMEImage(content, _subtype=sub_type)
                    else:
                        # Xử lý file thường (PDF, Zip, Docx...)
                        part = MIMEBase(main_type, sub_type)
                        part.set_payload(content)
                        encoders.encode_base64(part)

                    # Thêm header để Gmail hiểu đây là file
                    part.add_header('Content-Disposition', 'attachment', filename=filename)
                    message.attach(part)

            # Encode base64url và gửi
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            body = {'raw': raw}
            
            sent_message = self.service.users().messages().send(
                userId='me', body=body
            ).execute()
            
            print(f"✅ Đã gửi email đến {to_email}")
            return sent_message

        except Exception as e:
            print(f"❌ Lỗi gửi mail: {e}")
            return None

    # --- DELETE (Xóa Email - Chuyển vào thùng rác) ---
    def delete_email(self, msg_id):
        try:
            # trash() chuyển vào thùng rác, delete() xóa vĩnh viễn
            self.service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except Exception as e:
            print(f"Lỗi xóa mail: {e}")
            return False
    
    # --- CẬP NHẬT EMAIL: GẮN SAO, BỎ SAO, LƯU TRỮ ---
    def star_email(self, msg_id):
        try:
            self.service.users().messages().modify(
                userId='me', id=msg_id, body={'addLabelIds': ['STARRED']}
            ).execute()
            return True
        except Exception:
            return False

    def unstar_email(self, msg_id):
        try:
            self.service.users().messages().modify(
                userId='me', id=msg_id, body={'removeLabelIds': ['STARRED']}
            ).execute()
            return True
        except Exception:
            return False
    
    def archive_email(self, msg_id):
        try:
            # Gỡ nhãn INBOX
            self.service.users().messages().modify(
                userId='me', id=msg_id, body={'removeLabelIds': ['INBOX']}
            ).execute()
            return True
        except Exception:
            return False