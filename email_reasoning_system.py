from langgraph.graph import StateGraph, END
from typing import Dict, List, TypedDict
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from supabase.client import Client, create_client
from gmail_reader import get_gmail_service
import os
from dotenv import load_dotenv
import logging
import json
import base64
import io
import datetime
# Document processing imports
import docx
import fitz  # PyMuPDF
import pdfplumber

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class GraphState(TypedDict):
    user_id: str
    unread_emails: List[dict]
    current_email: dict
    context_emails: List[str]
    draft_reply: dict  # Will contain {"subject": "...", "body": "..."}
    error: str
    attachment_content: str  # New field for attachment content

class EmailReasoningSystem:
    def __init__(self, user_id: str):
        self.user_id = user_id
        
        # Initialize HuggingFace embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Initialize LLAMA 3 via Ollama
        self.llm = OllamaLLM(
            model="llama3",
            format="json"  # Request JSON response
        )
        
        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env file")
        
        self.supabase_client = create_client(supabase_url, supabase_key)
        
        # Test Supabase connection
        try:
            # Test connection by checking if documents table exists
            result = self.supabase_client.table("documents").select("id").limit(1).execute()
            logging.info(f"✓ Supabase connection successful. Found {len(result.data)} records.")
        except Exception as e:
            logging.error(f"❌ Supabase connection failed: {e}")
            raise
        
        # Initialize Supabase vector store
        try:
            self.vectorstore = SupabaseVectorStore(
                client=self.supabase_client,
                embedding=self.embeddings,
                table_name="documents",
                query_name="match_documents"
            )
            logging.info("✓ Supabase vector store initialized")
        except Exception as e:
            logging.error(f"❌ Failed to initialize vector store: {e}")
            raise
        
        self.gmail_service = get_gmail_service()

    def get_unread_emails_node(self, state: GraphState) -> GraphState:
        """Node to get all unread emails"""
        logging.info("--- STEP 1: GET ALL UNREAD EMAILS ---")
        try:
            # Get all unread emails
            results = self.gmail_service.users().messages().list(
                userId='me', 
                q='is:unread in:inbox',
                maxResults=50  # Limit to prevent overwhelming
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                return {**state, "error": "No unread emails found", "unread_emails": []}
            
            # Check which emails already have draft replies
            existing_drafts = self._get_existing_draft_emails()
            
            unread_emails = []
            for message in messages:
                email_id = message['id']
                
                # Skip if already processed (has draft reply)
                if email_id in existing_drafts:
                    logging.info(f"Skipping email {email_id} - already has draft")
                    continue
                
                # Get email details
                msg = self.gmail_service.users().messages().get(
                    userId='me', 
                    id=email_id
                ).execute()
                
                # Parse email
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'No Sender')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')
                message_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), '')
                
                # Extract body and attachments
                body = self._extract_email_body(msg['payload'])
                attachment_content = self._extract_attachments(msg['payload'])
                
                email_content = {
                    'id': email_id,
                    'subject': subject,
                    'from': sender,
                    'date': date,
                    'body': body,
                    'snippet': msg.get('snippet', ''),
                    'message_id': message_id,
                    'thread_id': msg.get('threadId', email_id),
                    'attachment_content': attachment_content
                }
                
                unread_emails.append(email_content)
            
            logging.info(f"✓ Found {len(unread_emails)} unread emails to process")
            return {**state, "unread_emails": unread_emails, "processed_count": 0}
            
        except Exception as e:
            logging.error(f"Error getting unread emails: {str(e)}")
            return {**state, "error": f"Error getting unread emails: {e}"}

    def _get_existing_draft_emails(self) -> set:
        """Get email IDs that already have draft replies"""
        try:
            # Check email_drafts table for existing drafts
            result = self.supabase_client.table("email_drafts").select("email_id").eq("user_id", self.user_id).execute()
            return {row["email_id"] for row in result.data}
        except Exception as e:
            logging.warning(f"Error checking existing drafts: {e}")
            return set()

    def _extract_attachments(self, payload) -> str:
        """Extract text content from attachments"""
        attachment_content = ""
        
        def process_parts(parts):
            nonlocal attachment_content
            for part in parts:
                if 'parts' in part:
                    process_parts(part['parts'])
                elif part.get('filename') and 'attachmentId' in part.get('body', {}):
                    filename = part['filename']
                    attachment_id = part['body']['attachmentId']
                    
                    # Only process text-based files
                    if self._is_text_file(filename):
                        try:
                            attachment = self.gmail_service.users().messages().attachments().get(
                                userId='me',
                                messageId=payload.get('messageId', ''),
                                id=attachment_id
                            ).execute()
                            
                            data = base64.urlsafe_b64decode(attachment['data'])
                            text_content = self._extract_text_from_file(data, filename)
                            
                            if text_content:
                                attachment_content += f"\n\n--- NỘI DUNG TỆP ĐÍNH KÈM ({filename}) ---\n{text_content}\n--- KẾT THÚC TỆP ĐÍNH KÈM ---\n"
                        
                        except Exception as e:
                            logging.warning(f"Error processing attachment {filename}: {e}")
        
        if 'parts' in payload:
            process_parts(payload['parts'])
        
        return attachment_content

    def _is_text_file(self, filename: str) -> bool:
        """Check if file is a supported text file"""
        return filename.lower().endswith(('.txt', '.docx', '.pdf'))

    def _extract_text_from_file(self, data: bytes, filename: str) -> str:
        """Extract text from different file types"""
        try:
            if filename.lower().endswith('.txt'):
                return data.decode('utf-8', errors='ignore')
            
            elif filename.lower().endswith('.docx'):
                doc = docx.Document(io.BytesIO(data))
                return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
            
            elif filename.lower().endswith('.pdf'):
                # Try with PyMuPDF first
                try:
                    doc = fitz.open(stream=data, filetype="pdf")
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    doc.close()
                    return text
                except:
                    # Fallback to pdfplumber
                    with pdfplumber.open(io.BytesIO(data)) as pdf:
                        text = ""
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"
                        return text
        
        except Exception as e:
            logging.warning(f"Error extracting text from {filename}: {e}")
            return ""

    def process_next_email_node(self, state: GraphState) -> GraphState:
        """Node to get next email to process"""
        if not state.get("unread_emails"):
            return {**state, "current_email": {}, "error": "No more emails to process"}
        
        current_email = state["unread_emails"].pop(0)
        logging.info(f"Processing email: {current_email['subject']}")
        
        return {**state, "current_email": current_email}

    def retrieve_context_node(self, state: GraphState) -> GraphState:
        """Node to search for context from sent emails (user-specific)"""
        logging.info("--- STEP 2: RETRIEVE USER-SPECIFIC CONTEXT ---")
        try:
            current_email = state.get("current_email", {})
            if not current_email:
                return {**state, "error": "No current email to search context for"}
            
            # Create query from subject, body, and attachments
            query_parts = [current_email['subject'], current_email['body']]
            if current_email.get('attachment_content'):
                query_parts.append(current_email['attachment_content'][:500])  # Limit attachment content in query
            
            query_text = " ".join(query_parts)
            logging.info(f"Searching for user context with query: {query_text[:100]}...")
            
            # Search for similar documents in Supabase (filtered by user_id)
            # Note: You'll need to modify the Supabase function to support user filtering
            similar_docs = self.vectorstore.similarity_search_with_score(
                query_text, 
                k=5,  # Tăng từ 3 lên 5 để có nhiều context hơn
                # Supabase filter syntax
                filter=f"metadata->>'user_id' = '{self.user_id}'"
            )
            
            if not similar_docs:
                logging.warning(f"No context found for user {self.user_id}")
                return {**state, "context_emails": []}
            
            context_emails = []
            seen_email_ids = set()
            
            for doc, score in similar_docs:
                metadata = doc.metadata
                email_id = metadata.get('email_id')
                
                if email_id not in seen_email_ids:
                    context_text = f"""
EMAIL REFERENCE:
Subject: {metadata.get('subject', '')}
To: {metadata.get('to', '')}
Date: {metadata.get('date', '')}
Content: {doc.page_content[:300]}...
Similarity: {float(1 - score):.2f}
"""
                    context_emails.append(context_text)
                    seen_email_ids.add(email_id)
            
            logging.info(f"✓ Found {len(context_emails)} relevant user emails")
            return {**state, "context_emails": context_emails}
            
        except Exception as e:
            error_msg = f"Error retrieving context: {str(e)}"
            logging.error(error_msg)
            return {**state, "context_emails": []}

    def generate_reply_node(self, state: GraphState) -> GraphState:
        """Node to generate reply using LLAMA 3 with attachment content"""
        logging.info("--- STEP 3: GENERATE REPLY WITH LLAMA 3 ---")
        try:
            current_email = state.get("current_email", {})
            if not current_email:
                return {**state, "error": "No current email to generate reply for"}
            
            context_list = state.get("context_emails", [])
            context = "\n---\n".join(context_list) if context_list else "Không tìm thấy email tham khảo nào."
            
            # Include attachment content in the prompt
            email_body = current_email['body']
            if current_email.get('attachment_content'):
                email_body += current_email['attachment_content']
            
            # Create prompt template
            template = """Bạn là một trợ lý email chuyên nghiệp, có nhiệm vụ soạn thảo email trả lời cho người dùng.

**Nhiệm vụ:**
1. Đọc kỹ "EMAIL MỚI NHẬN" (bao gồm cả nội dung tệp đính kèm nếu có).
2. Tham khảo văn phong từ "CÁC EMAIL THAM KHẢO" (nếu có).
3. Soạn một email trả lời ngắn gọn, chuyên nghiệp, đúng trọng tâm.

**Nguyên tắc:**
- Luôn giữ văn phong lịch sự, tích cực.
- Nếu có tệp đính kèm, hãy đề cập đến nội dung của nó trong phản hồi.
- Nếu không có đủ thông tin để trả lời, hãy nói rằng bạn sẽ kiểm tra và phản hồi sau.
- Trả lời bằng tiếng Việt.

**Định dạng đầu ra:**
Hãy trả lời bằng một đối tượng JSON duy nhất có cấu trúc sau:
{{
  "subject": "Tiêu đề email trả lời (có thể thêm Re:)",
  "body": "Nội dung email trả lời, bắt đầu bằng lời chào và kết thúc bằng lời cảm ơn."
}}

---
**EMAIL MỚI NHẬN:**
Từ: {sender}
Tiêu đề: {subject}
Nội dung:
{body}

---
**CÁC EMAIL THAM KHẢO (văn phong của tôi):**
{context}

---
**JSON ĐẦU RA:**
"""

            prompt_template = PromptTemplate.from_template(template)
            
            prompt = prompt_template.format(
                sender=current_email["from"],
                subject=current_email["subject"],
                body=email_body,
                context=context
            )
            
            logging.info("Calling LLAMA 3 via Ollama...")
            response = self.llm.invoke(prompt)
            
            # Parse JSON response
            try:
                response_clean = response.strip()
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                if response_clean.endswith('```'):
                    response_clean = response_clean[:-3]
                
                draft_reply = json.loads(response_clean)
                
                if not isinstance(draft_reply, dict) or "subject" not in draft_reply or "body" not in draft_reply:
                    raise ValueError("Invalid response format from LLM")
                
                logging.info(f"✓ Generated reply with subject: {draft_reply['subject'][:50]}...")
                return {**state, "draft_reply": draft_reply}
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse LLM JSON response: {e}")
                # Fallback response
                draft_reply = {
                    "subject": f"Re: {current_email['subject']}",
                    "body": f"""Chào {current_email['from'].split('@')[0]},
Cảm ơn bạn đã liên hệ về "{current_email['subject']}". 
Tôi đã nhận được thông tin và sẽ xem xét kỹ để phản hồi bạn sớm nhất có thể.
Trân trọng,"""
                }
                return {**state, "draft_reply": draft_reply}
            
        except Exception as e:
            logging.error(f"Error generating reply: {str(e)}")
            return {**state, "error": f"Error generating reply: {e}"}

    def create_draft_node(self, state: GraphState) -> GraphState:
        """Node to create draft reply and save to database"""
        logging.info("--- STEP 4: CREATE DRAFT REPLY ---")
        try:
            current_email = state.get("current_email", {})
            draft_reply = state.get("draft_reply", {})
            
            if not current_email or not draft_reply:
                return {**state, "error": "Missing current email or draft reply"}
            
            # Clean recipient email
            recipient = current_email["from"]
            import re
            email_match = re.search(r'<([^>]+)>', recipient)
            clean_recipient = email_match.group(1) if email_match else recipient.strip()
            
            # Create draft in Gmail
            draft_message = {
                'message': {
                    'raw': self._create_reply_message(
                        to=clean_recipient,
                        subject=draft_reply["subject"],
                        body=draft_reply["body"],
                        original_message_id=current_email.get("message_id", ""),
                        thread_id=current_email["id"]
                    ),
                    'threadId': current_email["id"]
                }
            }
            
            draft = self.gmail_service.users().drafts().create(
                userId='me',
                body=draft_message
            ).execute()
            
            # Save to database
            self._save_draft_to_db(current_email, draft_reply, draft['id'])
            
            processed_count = state.get("processed_count", 0) + 1
            logging.info(f"✓ Created draft {processed_count} with ID: {draft['id']}")
            
            return {**state, "processed_count": processed_count}
            
        except Exception as e:
            logging.error(f"Error creating draft reply: {str(e)}")
            # Cũng cần tăng counter khi có lỗi để tránh vòng lặp vô tận
            processed_count = state.get("processed_count", 0) + 1
            return {**state, "error": f"Error creating draft reply: {e}", "processed_count": processed_count}

    def _save_draft_to_db(self, email_content: dict, draft_reply: dict, draft_id: str):
        """Save draft information to database"""
        try:
            draft_data = {
                "user_id": self.user_id,
                "email_id": email_content["id"],
                "thread_id": email_content["thread_id"],
                "draft_id": draft_id,
                "subject": draft_reply["subject"],
                "body": draft_reply["body"],
                "recipient": email_content["from"],
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            
            self.supabase_client.table("email_drafts").insert(draft_data).execute()
            logging.info("✓ Saved draft to database")
            
        except Exception as e:
            logging.warning(f"Error saving draft to database: {e}")

    def _extract_email_body(self, payload):
        """Extract email body from payload"""
        body = ''
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
        else:
            if payload['body'].get('data'):
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body

    def _create_reply_message(self, to, subject, body, original_message_id="", thread_id=""):
        """Create a reply message for Gmail API with proper threading"""
        import email.mime.text
        from email.utils import make_msgid
        
        message = email.mime.text.MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        if original_message_id:
            message['In-Reply-To'] = original_message_id
            message['References'] = original_message_id
        
        message['Message-ID'] = make_msgid()
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return raw_message

def should_continue(state: GraphState) -> str:
    """Check if there are more emails to process"""
    if state.get("error") and "No more emails to process" not in state["error"]:
        return "end"
    elif state.get("unread_emails"):
        return "continue"
    else:
        return "end"

def create_reasoning_workflow(user_id: str):
    """Create workflow with LangGraph for bulk processing"""
    system = EmailReasoningSystem(user_id)
    
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("getUnreadEmails", system.get_unread_emails_node)
    workflow.add_node("processNext", system.process_next_email_node)
    workflow.add_node("retrieveContext", system.retrieve_context_node)
    workflow.add_node("generateReply", system.generate_reply_node)
    workflow.add_node("createDraft", system.create_draft_node)
    workflow.add_node("end", lambda x: x)
    
    # Define workflow connections
    workflow.set_entry_point("getUnreadEmails")
    workflow.add_edge("getUnreadEmails", "processNext")
    workflow.add_edge("processNext", "retrieveContext")
    workflow.add_edge("retrieveContext", "generateReply")
    workflow.add_edge("generateReply", "createDraft")
    
    # Conditional edge for continuing or ending
    workflow.add_conditional_edges(
        "createDraft",
        should_continue,
        {
            "continue": "processNext",
            "end": "end"
        }
    )
    
    return workflow.compile()

def main(user_id: str = "default_user"):
    """Run the bulk email reasoning system"""
    logging.info(f"🚀 Starting Bulk Email Reasoning System for user: {user_id}")
    
    try:
        app = create_reasoning_workflow(user_id)
        
        initial_state = GraphState(
            user_id=user_id,
            unread_emails=[],
            current_email={},
            context_emails=[],
            draft_reply={},
            processed_count=0,
            error="",
            attachment_content=""
        )
        
        final_state = app.invoke(initial_state)
        
        # Display results
        print("\n" + "="*60)
        print("📧 BULK EMAIL REASONING SYSTEM RESULTS")
        print("="*60)
        print(f"User ID: {user_id}")
        print(f"Processed emails: {final_state.get('processed_count', 0)}")
        
        if final_state.get("error") and "No more emails to process" not in final_state["error"]:
            print(f"❌ Error: {final_state['error']}")
        else:
            print("✅ All unread emails processed successfully!")
        
        return final_state
        
    except Exception as e:
        logging.error(f"System error: {str(e)}")
        return None

if __name__ == "__main__":
    result = main("bde57426-822d-4d41-8ad6-4a036fc6dc82")  # Replace with actual user ID