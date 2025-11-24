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
    def get_emails(self, max_results=10, page_token=None):
        try:
            print(f"🚀 Đang lấy email. Limit: {max_results}, Page Token: {page_token}")
            
            # Gọi API
            results = self.service.users().messages().list(
                userId='me', 
                maxResults=max_results,
                labelIds=['INBOX'],
                pageToken=page_token # <--- QUAN TRỌNG: Bên trái là tên Google, bên phải là biến của mình
            ).execute()
            
            messages = results.get('messages', [])
            next_token = results.get('nextPageToken') # Lấy token trang sau (nếu có)
            
            print(f"✅ Tìm thấy {len(messages)} email. Next Token: {next_token}")

            email_list = []
            if messages:
                for msg in messages:
                    try:
                        # Lấy chi tiết (dùng format metadata cho nhẹ)
                        msg_detail = self.service.users().messages().get(
                            userId='me', id=msg['id'], format='metadata'
                        ).execute()
                        
                        headers = msg_detail['payload']['headers']
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
                        
                        email_list.append({
                            "id": msg['id'],
                            "snippet": msg_detail.get('snippet'),
                            "subject": subject
                        })
                    except Exception:
                        continue 

            # Trả về cấu trúc mới gồm cả DATA và TOKEN
            return {
                "emails": email_list,
                "next_page_token": next_token
            }

        except Exception as e:
            print(f"❌ Lỗi đọc email: {e}")
            # Trả về rỗng để không bị sập app
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