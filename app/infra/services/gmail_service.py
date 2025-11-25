from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
import base64

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
    def get_emails(self, max_results=10, page_token=None):
        try:
            print(f"🚀 Đang lấy email. Limit: {max_results}")
            
            # Gọi API
            results = self.service.users().messages().list(
                userId='me', 
                maxResults=max_results,
                labelIds=['INBOX'],
                pageToken=page_token
            ).execute()
            
            messages = results.get('messages', [])
            next_token = results.get('nextPageToken')
            
            email_list = []
            if messages:
                for msg in messages:
                    try:
                        # Lấy chi tiết (metadata chứa headers: Subject, From, Date...)
                        msg_detail = self.service.users().messages().get(
                            userId='me', id=msg['id'], format='metadata'
                        ).execute()
                        
                        # --- XỬ LÝ HEADERS ---
                        # Chuyển list headers thành Dictionary cho dễ lấy
                        # Ví dụ: {'Subject': 'Chào bạn', 'From': 'Nam <nam@gmail.com>', ...}
                        headers_list = msg_detail['payload']['headers']
                        headers = {h['name']: h['value'] for h in headers_list}
                        
                        # Lấy thông tin (nếu không có thì để mặc định)
                        subject = headers.get('Subject', '(No Subject)')
                        sender = headers.get('From', '(Unknown Sender)') # Tên người gửi
                        date = headers.get('Date', '')                   # Ngày tháng
                        
                        email_list.append({
                            "id": msg['id'],
                            "snippet": msg_detail.get('snippet'), # Đoạn tóm tắt nội dung
                            "subject": subject,
                            "from": sender,  # <--- Mới thêm
                            "date": date     # <--- Mới thêm
                        })
                    except Exception:
                        continue 

            return {
                "emails": email_list,
                "next_page_token": next_token
            }

        except Exception as e:
            print(f"❌ Lỗi đọc email: {e}")
            return {"emails": [], "next_page_token": None}

    # --- CREATE (Gửi Email) ---
    def send_email(self, to_email, subject, body_content):
        try:
            message = MIMEText(body_content)
            message['to'] = to_email
            message['subject'] = subject
            # Encode message sang base64url (Yêu cầu của Gmail API)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            body = {'raw': raw}
            
            sent_message = self.service.users().messages().send(
                userId='me', body=body
            ).execute()
            return sent_message
        except Exception as e:
            print(f"Lỗi gửi mail: {e}")
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