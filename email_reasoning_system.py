from langgraph.graph import StateGraph, END
from typing import Dict, List, TypedDict
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM  # Updated import
from langchain_core.prompts import PromptTemplate
from supabase.client import Client, create_client
from gmail_reader import get_gmail_service
import os
from dotenv import load_dotenv
import logging
import json
import base64

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class GraphState(TypedDict):
    new_email_id: str
    user_id: str
    email_content: dict
    context_emails: List[str]
    draft_reply: dict  # Will contain {"subject": "...", "body": "..."}
    error: str

class EmailReasoningSystem:
    def __init__(self):
        # Initialize HuggingFace embeddings for vectorization
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Initialize LLAMA 3 via Ollama (Updated)
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

    def get_email_node(self, state: GraphState) -> GraphState:
        """Node to get new email content"""
        logging.info("--- STEP 1: GET EMAIL CONTENT ---")
        try:
            email_id = state.get("new_email_id")
            if not email_id:
                # Get latest unread email
                results = self.gmail_service.users().messages().list(
                    userId='me', 
                    q='is:unread in:inbox',
                    maxResults=1
                ).execute()
                
                messages = results.get('messages', [])
                if not messages:
                    return {**state, "error": "No new emails found"}
                
                email_id = messages[0]['id']
                state["new_email_id"] = email_id
            
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
            
            # Extract body
            body = self._extract_email_body(msg['payload'])
            
            email_content = {
                'id': email_id,
                'subject': subject,
                'from': sender,
                'date': date,
                'body': body,
                'snippet': msg.get('snippet', '')
            }
            
            logging.info(f"✓ Retrieved email: {subject}")
            return {**state, "email_content": email_content}
            
        except Exception as e:
            logging.error(f"Error getting email: {str(e)}")
            return {**state, "error": f"Error getting email: {e}"}

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

    def retrieve_context_node(self, state: GraphState) -> GraphState:
        """Node to search for context from sent emails"""
        logging.info("--- STEP 2: RETRIEVE CONTEXT ---")
        try:
            if not state.get("email_content"):
                return {**state, "error": "No email content to search context for"}
            
            email_content = state["email_content"]
            
            # Create query from subject and body
            query_text = f"{email_content['subject']} {email_content['body']}"
            logging.info(f"Searching for context with query: {query_text[:100]}...")
            
            # Check if there are any documents in the vector store
            try:
                # First, check if there are any documents
                doc_count = self.supabase_client.table("documents").select("id", count="exact").execute()
                total_docs = doc_count.count if hasattr(doc_count, 'count') else 0
                logging.info(f"Total documents in vector store: {total_docs}")
                
                if total_docs == 0:
                    logging.warning("⚠️ No documents found in vector store. Please run email_vectorizer.py first.")
                    return {**state, "context_emails": [], "error": "No vector data found. Run email_vectorizer.py first."}
                
            except Exception as e:
                logging.error(f"Error checking document count: {e}")
            
            # Search for similar documents in Supabase
            similar_docs = self.vectorstore.similarity_search_with_score(
                query_text, 
                k=3  # Get top 3 most similar results
            )
            
            context_emails = []
            seen_email_ids = set()
            
            for doc, score in similar_docs:
                metadata = doc.metadata
                email_id = metadata.get('email_id')
                
                # Avoid duplicate emails
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
            
            logging.info(f"✓ Found {len(context_emails)} relevant emails")
            return {**state, "context_emails": context_emails}
            
        except Exception as e:
            error_msg = f"Error retrieving context: {str(e)}"
            logging.error(error_msg)
            # Don't stop the workflow, continue with empty context
            return {**state, "context_emails": [], "error": ""}

    def generate_reply_node(self, state: GraphState) -> GraphState:
        """Node to generate reply using LLAMA 3"""
        logging.info("--- STEP 3: GENERATE REPLY WITH LLAMA 3 ---")
        try:
            if not state.get("email_content"):
                return {**state, "error": "No email content to generate reply for"}
            
            new_email = state["email_content"]
            context_list = state.get("context_emails", [])
            context = "\n---\n".join(context_list) if context_list else "Không tìm thấy email tham khảo nào."
            
            # Create prompt template
            template = """Bạn là một trợ lý email chuyên nghiệp, có nhiệm vụ soạn thảo email trả lời cho người dùng.

**Nhiệm vụ:**
1. Đọc kỹ "EMAIL MỚI NHẬN".
2. Tham khảo văn phong từ "CÁC EMAIL THAM KHẢO" (nếu có).
3. Soạn một email trả lời ngắn gọn, chuyên nghiệp, đúng trọng tâm.

**Nguyên tắc:**
- Luôn giữ văn phong lịch sự, tích cực.
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
                sender=new_email["from"],
                subject=new_email["subject"],
                body=new_email["body"],
                context=context
            )
            
            logging.info("Calling LLAMA 3 via Ollama...")
            
            # Call LLAMA 3 via Ollama
            response = self.llm.invoke(prompt)
            
            logging.info(f"Raw LLM response: {response[:200]}...")
            
            # Parse JSON response
            try:
                # Clean response if needed
                response_clean = response.strip()
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                if response_clean.endswith('```'):
                    response_clean = response_clean[:-3]
                
                draft_reply = json.loads(response_clean)
                
                # Validate response structure
                if not isinstance(draft_reply, dict) or "subject" not in draft_reply or "body" not in draft_reply:
                    raise ValueError("Invalid response format from LLM")
                
                logging.info(f"✓ Generated reply with subject: {draft_reply['subject'][:50]}...")
                return {**state, "draft_reply": draft_reply}
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse LLM JSON response: {e}")
                logging.error(f"Raw response was: {response}")
                # Fallback response
                draft_reply = {
                    "subject": f"Re: {new_email['subject']}",
                    "body": "Chào bạn,\n\nCảm ơn bạn đã liên hệ. Tôi đã nhận được email của bạn và sẽ phản hồi sớm nhất có thể.\n\nTrân trọng!"
                }
                return {**state, "draft_reply": draft_reply}
            
        except Exception as e:
            logging.error(f"Error generating reply: {str(e)}")
            return {**state, "error": f"Error generating reply: {e}"}

    def create_draft_node(self, state: GraphState) -> GraphState:
        """Node to create draft in Gmail"""
        logging.info("--- STEP 4: CREATE DRAFT IN GMAIL ---")
        try:
            if not state.get("email_content") or not state.get("draft_reply"):
                return {**state, "error": "Missing email content or draft reply"}
            
            email_content = state["email_content"]
            draft_reply = state["draft_reply"]
            
            # Clean the recipient email address
            recipient = email_content["from"]
            import re
            email_match = re.search(r'<([^>]+)>', recipient)
            if email_match:
                clean_recipient = email_match.group(1)
            else:
                clean_recipient = recipient.strip()
            
            logging.info(f"Creating draft to: {clean_recipient}")
            
            # Create draft message
            draft_message = {
                'message': {
                    'raw': self._create_message(
                        to=clean_recipient,  # Use cleaned email
                        subject=draft_reply["subject"],
                        body=draft_reply["body"]
                    )
                }
            }
            
            # Create draft in Gmail
            draft = self.gmail_service.users().drafts().create(
                userId='me',
                body=draft_message
            ).execute()
            
            logging.info(f"✓ Created draft with ID: {draft['id']}")
            return {**state, "draft_id": draft['id']}
            
        except Exception as e:
            logging.error(f"Error creating draft: {str(e)}")
            return {**state, "error": f"Error creating draft: {e}"}

    def _create_message(self, to, subject, body):
        """Create a message for Gmail API"""
        import email.mime.text
        
        message = email.mime.text.MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return raw_message

def create_reasoning_workflow():
    """Create workflow with LangGraph"""
    system = EmailReasoningSystem()
    
    # Create state graph
    workflow = StateGraph(GraphState)
    
    # Add nodes to graph
    workflow.add_node("getEmail", system.get_email_node)
    workflow.add_node("retrieveContext", system.retrieve_context_node)
    workflow.add_node("generateReply", system.generate_reply_node)
    workflow.add_node("createDraft", system.create_draft_node)
    
    # Define workflow connections
    workflow.set_entry_point("getEmail")
    workflow.add_edge("getEmail", "retrieveContext")
    workflow.add_edge("retrieveContext", "generateReply")
    workflow.add_edge("generateReply", "createDraft")
    workflow.add_edge("createDraft", END)
    
    return workflow.compile()

def main():
    """Run the email reasoning system"""
    logging.info("🚀 Starting Email Reasoning System with LLAMA 3...")
    
    try:
        # Create workflow
        app = create_reasoning_workflow()
        
        # Initialize state
        initial_state = GraphState(
            new_email_id="",  # Will be auto-detected
            user_id="me",
            email_content={},
            context_emails=[],
            draft_reply={},
            error=""
        )
        
        # Run workflow
        final_state = app.invoke(initial_state)
        
        # Display results
        print("\n" + "="*60)
        print("📧 EMAIL REASONING SYSTEM RESULTS")
        print("="*60)
        
        if final_state.get("error"):
            print(f"\n❌ ERROR OCCURRED:")
            print(final_state["error"])
            # Don't return early if it's just a context error
            if "No vector data found" not in final_state["error"]:
                return final_state
        
        if final_state.get("email_content"):
            email = final_state["email_content"]
            print(f"\n📨 NEW EMAIL RECEIVED:")
            print(f"From: {email['from']}")
            print(f"Subject: {email['subject']}")
            print(f"Content: {email['body'][:200]}...")
        
        print(f"\n🔍 FOUND: {len(final_state.get('context_emails', []))} relevant emails")
        
        if final_state.get("draft_reply"):
            draft = final_state["draft_reply"]
            print(f"\n🤖 GENERATED REPLY:")
            print(f"Subject: {draft['subject']}")
            print("-" * 40)
            print(draft['body'])
            print("-" * 40)
        
        if final_state.get("draft_id"):
            print(f"\n✅ DRAFT CREATED: ID {final_state['draft_id']}")
        
        return final_state
        
    except Exception as e:
        logging.error(f"System error: {str(e)}")
        return None

if __name__ == "__main__":
    result = main()