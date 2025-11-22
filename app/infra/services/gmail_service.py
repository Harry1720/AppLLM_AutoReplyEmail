from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
import base64

class GmailService:
    def __init__(self, token_info: dict):
        # Token info là thông tin OAuth nhận được từ FE hoặc DB
        self.creds = Credentials.from_authorized_user_info(token_info)
        self.service = build('gmail', 'v1', credentials=self.creds)

    # --- READ (Đọc danh sách Email) ---
    def get_emails(self, max_results=10):
        try:
            # Gọi API lấy danh sách ID tin nhắn
            results = self.service.users().messages().list(
                userId='me', maxResults=max_results
            ).execute()
            messages = results.get('messages', [])
            
            email_list = []
            # Lấy chi tiết từng mail (snippet, tiêu đề)
            for msg in messages:
                msg_detail = self.service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata'
                ).execute()
                
                # Trích xuất tiêu đề (Subject) từ headers
                headers = msg_detail['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
                
                email_list.append({
                    "id": msg['id'],
                    "snippet": msg_detail.get('snippet'),
                    "subject": subject
                })
            return email_list
        except Exception as e:
            print(f"Lỗi đọc email: {e}")
            return []

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