from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.utils import parseaddr
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
            # Body content từ FE đã có format HTML (bao gồm \n, <br>, <p>...)
            # Giữ nguyên định dạng bằng cách sử dụng 'html' subtype
            msg_text = MIMEText(body_content, 'html', 'utf-8')
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
        

    # --- HÀM LẤY DANH SÁCH BẢN NHÁP (DRAFTS) ---
    def get_drafts(self, max_results=10, page_token=None):
        try:
            print(f"🚀 Đang lấy Drafts. Limit: {max_results}")
            
            # 1. Lấy danh sách ID Drafts
            results = self.service.users().drafts().list(
                userId='me', 
                maxResults=max_results,
                pageToken=page_token
            ).execute()
            
            drafts = results.get('drafts', [])
            next_token = results.get('nextPageToken')
            
            if not drafts:
                return {"drafts": [], "next_page_token": None}

            # 2. Dùng Batch Request để lấy chi tiết từng Draft
            draft_list = []
            
            def batch_callback(request_id, response, exception):
                if exception:
                    print(f"⚠️ Lỗi đọc draft {request_id}: {exception}")
                else:
                    try:
                        # Cấu trúc Draft: {'id': '...', 'message': {'payload': ...}}
                        msg = response.get('message', {})
                        payload = msg.get('payload', {})
                        headers_list = payload.get('headers', [])
                        
                        # Chuyển headers thành dict
                        headers = {h['name']: h['value'] for h in headers_list}
                        
                        draft_list.append({
                            "id": response['id'], # ID của Draft (để edit hoặc gửi)
                            "msg_id": msg['id'],  # ID của Message bên trong
                            "snippet": msg.get('snippet'),
                            "subject": headers.get('Subject', '(No Subject)'),
                            "to": headers.get('To', '(No Recipient)'), # Draft quan trọng người nhận
                            "date": headers.get('Date', '')
                        })
                    except Exception as e:
                        print(f"Lỗi parse draft: {e}")

            batch = self.service.new_batch_http_request(callback=batch_callback)

            for d in drafts:
                batch.add(
                    self.service.users().drafts().get(
                        userId='me', 
                        id=d['id'], 
                        format='metadata'
                    )
                )
            
            batch.execute()
            
            print(f"✅ Đã tải xong {len(draft_list)} bản nháp.")
            return {
                "drafts": draft_list, 
                "next_page_token": next_token
            }

        except Exception as e:
            print(f"❌ Lỗi lấy drafts: {e}")
            return {"drafts": [], "next_page_token": None}


    # --- HÀM LẤY CHI TIẾT MỘT BẢN NHÁP (DRAFT DETAIL) ---
    def get_draft_detail(self, draft_id):
        try:
            print(f"🚀 Đang lấy chi tiết draft ID: {draft_id}")
            
            # Gọi API lấy full draft
            draft = self.service.users().drafts().get(
                userId='me', 
                id=draft_id, 
                format='full'
            ).execute()
            
            # Cấu trúc: draft = {'id': '...', 'message': {...}}
            msg = draft.get('message', {})
            payload = msg.get('payload', {})
            headers_list = payload.get('headers', [])
            
            # Chuyển headers thành dict
            headers = {h['name']: h['value'] for h in headers_list}
            
            # Lấy body của draft (dùng hàm đệ quy có sẵn)
            body_html = self._get_body_from_payload(payload)
            
            result = {
                "id": draft['id'],  # Draft ID
                "msg_id": msg.get('id'),  # Message ID
                "subject": headers.get('Subject', '(No Subject)'),
                "from": headers.get('From', ''),
                "to": headers.get('To', ''),
                "date": headers.get('Date', ''),
                "body": body_html,
                "snippet": msg.get('snippet'),
                "thread_id": msg.get('threadId')
            }
            
            print(f"✅ Đã lấy chi tiết draft thành công")
            return result
            
        except Exception as e:
            print(f"❌ Lỗi lấy chi tiết draft: {e}")
            return None
        

    # --- 1. ĐÁNH DẤU ĐÃ ĐỌC (Mark as Read) ---
    def mark_as_read(self, msg_id):
        try:
            # Logic: Gỡ nhãn 'UNREAD' ra khỏi email
            self.service.users().messages().modify(
                userId='me', 
                id=msg_id, 
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print(f"✅ Đã đánh dấu ĐÃ ĐỌC cho email {msg_id}")
            return True
        except Exception as e:
            print(f"❌ Lỗi mark_as_read: {e}")
            return False

    # --- 2. ĐÁNH DẤU CHƯA ĐỌC (Mark as Unread) ---
    def mark_as_unread(self, msg_id):
        try:
            # Logic: Thêm nhãn 'UNREAD' vào email
            self.service.users().messages().modify(
                userId='me', 
                id=msg_id, 
                body={'addLabelIds': ['UNREAD']}
            ).execute()
            print(f"✅ Đã đánh dấu CHƯA ĐỌC cho email {msg_id}")
            return True
        except Exception as e:
            print(f"❌ Lỗi mark_as_unread: {e}")
            return False
            

    def reply_email(self, original_msg_id, body_content, attachments=None):
        try:
            print(f"🚀 Đang chuẩn bị Reply email: {original_msg_id}")

            # 1. Lấy thông tin email gốc
            try:
                original_msg = self.service.users().messages().get(
                    userId='me', id=original_msg_id, format='metadata'
                ).execute()
            except Exception as e:
                print(f"❌ Lỗi bước 1 (Lấy email gốc): ID có thể sai. {e}")
                raise ValueError("Không tìm thấy email gốc (Sai ID?)")

            # 2. Xử lý Headers
            try:
                payload = original_msg.get('payload', {})
                headers_list = payload.get('headers', [])
                headers = {h['name']: h['value'] for h in headers_list}
                
                # Lấy người nhận
                reply_to_raw = headers.get('Reply-To', headers.get('From', ''))
                name, clean_email = parseaddr(reply_to_raw)
                
                if not clean_email:
                    print(f"⚠️ Không tìm thấy email trong: {reply_to_raw}")
                    # Fallback: Cố gắng lấy từ header khác hoặc báo lỗi rõ ràng
                    raise ValueError(f"Không lấy được địa chỉ người nhận từ: {reply_to_raw}")

                print(f"📧 Sẽ gửi tới: {clean_email}")

                # Lấy Subject và ThreadId
                subject = headers.get('Subject', '')
                if not subject.lower().startswith('re:'):
                    subject = f"Re: {subject}"
                
                thread_id = original_msg.get('threadId')
                msg_id_header = headers.get('Message-ID')
                
            except Exception as e:
                print(f"❌ Lỗi bước 2 (Xử lý header): {e}")
                raise ValueError("Email gốc bị lỗi cấu trúc, không đọc được Header")

            # 3. Tạo nội dung và Gửi
            try:
                message = MIMEMultipart()
                message['to'] = clean_email
                message['subject'] = subject
                
                if msg_id_header:
                    message['In-Reply-To'] = msg_id_header
                    message['References'] = msg_id_header

                # Đính kèm nội dung - giữ nguyên định dạng HTML từ FE
                message.attach(MIMEText(body_content, 'html', 'utf-8'))

                # (Code xử lý file giữ nguyên...)
                if attachments:
                    for file_data in attachments:
                        # ... (Code cũ của bạn) ...
                        pass

                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                body = {'raw': raw}
                
                if thread_id:
                    body['threadId'] = thread_id

                sent_message = self.service.users().messages().send(
                    userId='me', body=body
                ).execute()
                
                print(f"✅ Đã gửi thành công! ID: {sent_message['id']}")
                return sent_message

            except Exception as e:
                print(f"❌ Lỗi bước 3 (Gửi đi): {e}")
                raise e

        except Exception as e:
            # Ném lỗi ra ngoài để Swagger hiển thị
            raise e
        

    # --- HÀM CẬP NHẬT BẢN NHÁP (Edit Draft) ---
    def update_draft(self, draft_id, to, subject, body_content):
        try:
            print(f"✏️ Đang chỉnh sửa draft {draft_id}...")

            # 1. Đóng gói nội dung mới (Giống hệt lúc tạo/gửi)
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            
            # Lưu ý: Sửa draft thường chỉ sửa chữ, nên mình làm đơn giản không file
            # Nếu muốn sửa file thì copy logic attachment từ hàm send_email qua
            msg_text = MIMEText(body_content, 'html', 'utf-8')
            message.attach(msg_text)

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # 2. Gọi lệnh UPDATE
            # Cấu trúc body của Update giống hệt Create
            updated_draft = self.service.users().drafts().update(
                userId='me', 
                id=draft_id, # Phải có ID để biết sửa cái nào
                body={'message': {'raw': raw}}
            ).execute()
            
            print(f"✅ Đã cập nhật draft thành công!")
            return updated_draft

        except Exception as e:
            print(f"❌ Lỗi update draft: {e}")
            return None
        

    # --- HÀM GỬI BẢN NHÁP (Release Draft) ---
    def send_draft(self, draft_id):
        try:
            print(f"🚀 Đang gửi bản nháp ID: {draft_id}")
            
            # Lệnh này sẽ biến Draft thành Sent Message ngay lập tức
            sent_message = self.service.users().drafts().send(
                userId='me', 
                body={'id': draft_id} # Chỉ cần gửi ID là đủ
            ).execute()
            
            print(f"✅ Đã gửi bản nháp thành công! Message ID: {sent_message['id']}")
            return sent_message

        except Exception as e:
            print(f"❌ Lỗi gửi draft: {e}")
            return None
        

    # --- HÀM XÓA BẢN NHÁP (Discard Draft) ---
    def delete_draft(self, draft_id):
        try:
            print(f"🗑️ Đang xóa vĩnh viễn bản nháp {draft_id}...")
            
            # Lệnh này xóa vĩnh viễn draft (không vào thùng rác)
            self.service.users().drafts().delete(
                userId='me', 
                id=draft_id
            ).execute()
            
            print(f"✅ Đã xóa bản nháp thành công!")
            return True

        except Exception as e:
            print(f"❌ Lỗi xóa draft: {e}")
            return False