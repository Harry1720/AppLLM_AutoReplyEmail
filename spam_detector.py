from langgraph.graph import StateGraph
from typing import Dict, TypedDict
from gmail_reader import get_todays_emails, get_gmail_service
from dotenv import load_dotenv
import openai
import time
import logging
import re
import os

load_dotenv() 

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# OpenAI client
client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

class GmailLabeler:
    def __init__(self):
        self.service = get_gmail_service()
        self.label_id = self._get_or_create_label()

    def _get_or_create_label(self):
        results = self.service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        
        for label in labels:
            if label['name'] == 'Unsubscribe':
                return label['id']
        
        label = {
            'name': 'Unsubscribe',
            'messageListVisibility': 'show',
            'labelListVisibility': 'labelShow'
        }
        created_label = self.service.users().labels().create(userId='me', body=label).execute()
        return created_label['id']

    def label_spam(self, email_id: str) -> bool:
        """Label an email as spam"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': [self.label_id]}
            ).execute()
            return True
        except Exception as e:
            logging.error(f"Failed to label email: {str(e)}")
            return False

def check_spam_score(email: dict) -> float:
    """Get spam score using basic rules"""
    score = 0.0
    text = f"{email['from']} {email['subject']} {email['snippet']}".lower()
    
    # Common spam indicators
    spam_patterns = [
        (r'\b(viagra|cialis|pharmacy)\b', 2.0),
        (r'\$([\d,]+)', 1.0),
        (r'\b(lottery|winner|prize|won)\b', 1.5),
        (r'\b(urgent|action required|immediate)\b', 0.5),
        (r'\b(cryptocurrency|crypto|bitcoin|btc)\b', 1.0),
        (r'\b(survey|feedback|opinion)\b', 0.3),
        (r'[!]{2,}', 0.5),
        (r'\b(unsubscribe|opt[ -]?out)\b', 0.2),
        (r'\b(limited time|offer expires|act now)\b', 1.0),
        (r'\b(no obligation|risk[ -]?free)\b', 1.0),
    ]
    
    for pattern, weight in spam_patterns:
        if re.search(pattern, text):
            score += weight
    
    # Check for excessive capitalization
    caps_ratio = sum(1 for c in email['subject'] if c.isupper()) / (len(email['subject']) + 1)
    if caps_ratio > 0.3:
        score += 1.0
    
    return score

class EmailState(TypedDict):
    emails: list
    safe_emails: list
    spam_emails: list
    uncertain_emails: list
    api_calls: int
    labeler: GmailLabeler

def initialize_state() -> EmailState:
    """Initialize workflow state"""
    return {
        "emails": get_todays_emails(),
        "safe_emails": [],
        "spam_emails": [],
        "uncertain_emails": [],
        "api_calls": 0,
        "labeler": GmailLabeler(),
    }

def pre_filter(state: EmailState) -> EmailState:
    """First pass: Filter using basic rules and spam checker"""
    safe_domains = {
        'linkedin.com', 'github.com', 'google.com', 'microsoft.com', 'apple.com',
        'amazon.com', 'slack.com', 'zoom.us', 'dropbox.com', 'atlassian.com',
        'salesforce.com', 'zendesk.com', 'jira.com', 'asana.com', 'chase.com'
    }
    
    for email in state["emails"]:
        sender = email['from'].lower()
        
        # Safe domain check
        if any(domain in sender for domain in safe_domains):
            state["safe_emails"].append(email)
            logging.info(f"✓ Safe domain: {email['subject']}")
            continue
        
        # Get spam score using our basic checker
        spam_score = check_spam_score(email)
        
        if spam_score > 3.0:  # High confidence spam
            state["spam_emails"].append(email)
            logging.info(f"⚠ High spam score: {email['subject']} (score: {spam_score})")
        elif spam_score < 1.0:  # Likely safe
            state["safe_emails"].append(email)
            logging.info(f"✓ Low spam score: {email['subject']}")
        else:  # Uncertain cases
            state["uncertain_emails"].append(email)
            logging.info(f"? Uncertain: {email['subject']} (score: {spam_score})")
    
    state["emails"] = state["uncertain_emails"]
    state["uncertain_emails"] = []
    
    logging.info(f"""
Pre-filter results:
Safe emails: {len(state['safe_emails'])}
Obvious spam: {len(state['spam_emails'])}
Needs AI analysis: {len(state['emails'])}
""")
    return state

def analyze_email(state: EmailState) -> EmailState:
    """Second pass: Use OpenAI for uncertain cases"""
    if not state["emails"]:
        return state
        
    email = state["emails"].pop(0)
    try:
        state["api_calls"] += 1
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a spam detector. 
                Only mark as SPAM if very confident. When in doubt, mark as NOT_SPAM.
                Respond with SPAM or NOT_SPAM only."""},
                {"role": "user", "content": f"""Analyze this uncertain email:
                From: {email['from']}
                Subject: {email['subject']}
                Content: {email['snippet']}
                
                Consider:
                1. Sender credibility
                2. Content legitimacy
                3. Urgency/pressure tactics
                4. Professional tone"""}
            ],
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip().upper()
        if "SPAM" in result:
            state["spam_emails"].append(email)
            if state["labeler"].label_spam(email['id']):
                logging.info(f"⚠ AI confirmed and labeled spam: {email['subject']}")
            else:
                logging.info(f"⚠ AI confirmed spam but labeling failed: {email['subject']}")
        else:
            state["safe_emails"].append(email)
            logging.info(f"✓ AI confirmed safe: {email['subject']}")
            
    except Exception as e:
        logging.error(f"Error in AI analysis: {str(e)}")
        state["safe_emails"].append(email)
    
    return state

def should_continue(state: EmailState) -> bool:
    """Check if there are more emails to process"""
    MAX_API_CALLS = 50
    return bool(state["emails"] and state["api_calls"] < MAX_API_CALLS)

def run_workflow():
    """Run the spam detection workflow"""
    start_time = time.time()
    logging.info("Starting spam detection")
    
    # Create workflow
    workflow = StateGraph(EmailState)
    
    # Add nodes
    workflow.add_node("pre_filter", pre_filter)
    workflow.add_node("analyze", analyze_email)
    workflow.add_node("end", lambda x: x)
    
    # Define workflow
    workflow.set_entry_point("pre_filter")
    workflow.add_edge("pre_filter", "analyze")
    workflow.add_conditional_edges(
        "analyze",
        should_continue,
        {
            True: "analyze",
            False: "end"
        }
    )
    
    # Run workflow
    app = workflow.compile()
    final_state = app.invoke(initialize_state())
    
    # Show results
    execution_time = time.time() - start_time
    logging.info(f"""
=== Spam Detection Complete ===
Total emails processed: {len(final_state['safe_emails']) + len(final_state['spam_emails'])}
Safe emails: {len(final_state['safe_emails'])}
Spam detected and labeled: {len(final_state['spam_emails'])}
API calls made: {final_state['api_calls']}
Time taken: {execution_time:.2f}s
============================
""")
    
    return final_state["spam_emails"]

if __name__ == "__main__":
    spam_emails = run_workflow() 