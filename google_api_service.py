import os.path
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar.events'
]

import json

def get_credentials():
    """Gets valid user credentials from storage or initiates OAuth2 flow."""
    creds = None
    
    # 1. Try to load from Environment Variables (Production / Secret Manager)
    env_token = os.environ.get("GOOGLE_OAUTH_TOKEN")
    env_creds = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
    
    if env_token:
        token_info = json.loads(env_token)
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    elif os.path.exists('token.json'):
        # 2. Fallback to local file (Development)
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if env_creds:
                client_config = json.loads(env_creds)
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            else:
                print("WARNING: Neither env vars nor credentials.json found. Google API skipped.")
                return None
            
            # Run local server, requires user to approve in browser
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run (only if using local files)
        if not env_token:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
    return creds

def send_gmail(to_email: str, subject: str, html_body: str) -> dict:
    """Sends an email using the Gmail API."""
    creds = get_credentials()
    if not creds:
        return {"status": "error", "message": "No credentials.json available"}
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = EmailMessage()
        message.set_content("Please enable HTML to view this email.")
        message.add_alternative(html_body, subtype='html')
        message['To'] = to_email
        message['From'] = "me"
        message['Subject'] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        return {"status": "success", "message_id": send_message['id']}
    except HttpError as error:
        print(f"An error occurred sending Gmail: {error}")
        return {"status": "error", "message": str(error)}

def create_calendar_event(attendee_email: str, title: str, description: str, start_time: str, end_time: str) -> dict:
    """Creates a Google Calendar event and invites the user."""
    creds = get_credentials()
    if not creds:
        return {"status": "error", "message": "No credentials.json available"}
        
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = {
          'summary': title,
          'description': description,
          'start': {
            'dateTime': start_time,
          },
          'end': {
            'dateTime': end_time,
          },
          'attendees': [
            {'email': attendee_email},
          ],
          'reminders': {
            'useDefault': False,
            'overrides': [
              {'method': 'email', 'minutes': 24 * 60},
              {'method': 'popup', 'minutes': 10},
            ],
          },
        }
        
        event = service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
        return {"status": "success", "event_id": event.get('id'), "link": event.get('htmlLink')}
    except HttpError as error:
        print(f"An error occurred creating calendar event: {error}")
        return {"status": "error", "message": str(error)}

def send_welcome_email(to_email: str, user_id: str) -> dict:
    """Sends a welcome email to a newly signed up user."""
    subject = "Welcome to Curl Chemist! 🧪"
    html_body = (
        f"<h2>Welcome to Curl Chemist, {user_id}!</h2>"
        f"<p>We're thrilled to have you. Your personal AI chemist is ready to analyze your hair routine.</p>"
        f"<p>Start by adding some products to your shelf, and we'll automatically detect any chemical conflicts or missing necessities.</p>"
        f"<br>"
        f"<p>Stay curly,</p>"
        f"<p><strong>Your Curl Chemist Agent</strong></p>"
    )
    return send_gmail(to_email, subject, html_body)
