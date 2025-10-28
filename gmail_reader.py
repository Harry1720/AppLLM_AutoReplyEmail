from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os
import datetime
from email.utils import parsedate_to_datetime

print("calling main....")


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.labels',
    'https://www.googleapis.com/auth/gmail.modify'
]

def get_gmail_service():
    """Get or create Gmail API service"""
    creds = None
    
    # Load existing credentials if available
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def get_todays_emails():
    """Fetch today's emails from Gmail"""
    service = get_gmail_service()
    
    # Get today's date
    today = datetime.datetime.now().date()
    
    # Search for today's emails
    query = f'after:{today.strftime("%Y/%m/%d")}'
    
    try:
        # Get list of messages
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print('No emails found for today.')
            return []
        
        emails = []
        for message in messages:
            # Get full message details
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            id = message['id']
            # Extract headers
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'No Sender')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')
            
            # Extract msg body
            body = ''
            if 'parts' in msg['payload']:
                for part in msg['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body = part['body']['data']
                        break
            else:
                body = msg['payload']['body']['data']
            
            # Decode the body
            if body:
                import base64
                body = base64.urlsafe_b64decode(body).decode('utf-8')
            
            emails.append({
                'id': id,
                'subject': subject,
                'from': sender,
                'date': date,
                'snippet': msg['snippet'],
                'body': body
            })
        
        return emails
            
    except Exception as error:
        print(f'An error occurred: {error}')
        return []

def main():
    print("calling main....")
    emails = get_todays_emails()
    
    print(f"\nFound {len(emails)} emails from today:")
    for i, email in enumerate(emails, 1):
        print(f"\nEmail {i}:")
        print(f"From: {email['from']}")
        print(f"Subject: {email['subject']}")
        print(f"Date: {email['date']}")
        print(f"Snippet: {email['snippet']}")
        print("-" * 50)

if __name__ == '__main__':
    main()