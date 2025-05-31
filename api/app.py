import os
import json
import re
from datetime import datetime, time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import openai
from firecrawl import FirecrawlApp
import resend
import pytz

# Initialize APIs
openai.api_key = os.getenv("OPENAI_API_KEY")
firecrawl_app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
resend.api_key = os.getenv("RESEND_API_KEY")

# Initialize FastAPI
app = FastAPI()

# Enable CORS for Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data storage file
DATA_FILE = "users.json"

# Available sources
AVAILABLE_SOURCES = {
    "medium": {"url": "https://medium.com/tag/artificial-intelligence", "topics": ["AI", "productivity"]},
    "google_news_tech": {"url": "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB", "topics": ["technology"]},
    "google_news_business": {"url": "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB", "topics": ["business"]},
    "google_news_world": {"url": "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp0Y1RjU0FtVnVHZ0pWVXlnQVAB", "topics": ["world news"]},
    "book_summaries": {"url": "https://fourminutebooks.com/book-summaries/", "topics": ["self-help", "productivity"]}
}

class UserInput(BaseModel):
    email: str
    message: str

class UserData(BaseModel):
    email: EmailStr
    sources: List[str] = ["medium", "google_news_tech"]
    timezone: str = "America/Los_Angeles"
    send_time: str = "08:00"

def load_users() -> Dict:
    """Load users from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users: Dict):
    """Save users to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def parse_user_intent(message: str, email: str) -> Dict:
    """Use OpenAI to parse user intent from natural language"""
    prompt = f"""
    Parse the user's intent from their message. The user email is: {email}
    
    Message: "{message}"
    
    Possible intents:
    - add_source: User wants to add a news source (extract source name)
    - remove_source: User wants to remove a news source (extract source name)  
    - change_time: User wants to change delivery time (extract time in HH:MM format)
    - set_timezone: User wants to set timezone (extract timezone)
    - unsubscribe: User wants to unsubscribe
    - view_sources: User wants to see their current sources
    - help: User needs help or the intent is unclear
    
    Available sources: medium, google_news_tech, google_news_business, google_news_world, book_summaries
    
    Return a JSON object with:
    - intent: one of the above intents
    - source: the source name if applicable (standardized to match available sources)
    - time: the time if applicable (in HH:MM format)
    - timezone: the timezone if applicable
    """
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that parses user intents."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def scrape_content(source: str) -> List[Dict]:
    """Scrape content from a source using Firecrawl"""
    source_info = AVAILABLE_SOURCES.get(source)
    if not source_info:
        return []
    
    try:
        # Scrape the URL
        data = firecrawl_app.scrape_url(
            source_info["url"],
            params={
                "formats": ["markdown"],
                "onlyMainContent": True
            }
        )
        
        # Extract relevant content using OpenAI
        prompt = f"""
        Extract the most relevant and interesting content from this source.
        Topics of interest: {', '.join(source_info['topics'])}
        
        Content:
        {data.get('markdown', '')[:3000]}
        
        Return a JSON object with an "items" array containing 5-10 items, each with:
        - title: Brief descriptive title
        - summary: 2-3 bullet points summarizing key information
        - link: URL if available (or null)
        """
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a content curator that extracts relevant information."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("items", [])
        
    except Exception as e:
        print(f"Error scraping {source}: {str(e)}")
        return []

def create_digest(user_data: UserData) -> str:
    """Create email digest content"""
    all_content = []
    
    # Scrape content from each source
    for source in user_data.sources:
        content = scrape_content(source)
        all_content.extend(content)
    
    # Format the digest using OpenAI
    prompt = f"""
    Create a morning news digest email from the following content.
    Organize by topic and relevance. Format as HTML with:
    - Clear title indicating this is a daily digest
    - Sections by topic
    - Bullet points for easy reading
    - Include source links where available
    - Professional and clean formatting
    
    Content:
    {json.dumps(all_content[:20])}
    """
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a professional newsletter writer."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content

def send_digest(email: str, content: str):
    """Send digest email using Resend"""
    try:
        # For development/testing without Resend API key
        if not resend.api_key:
            print(f"Would send email to {email}")
            print(f"Subject: Your Daily News Digest - {datetime.now().strftime('%B %d, %Y')}")
            print("Content preview:", content[:200])
            return
            
        resend.Emails.send({
            "from": "News Digest <digest@resend.dev>",
            "to": email,
            "subject": f"Your Daily News Digest - {datetime.now().strftime('%B %d, %Y')}",
            "html": content
        })
    except Exception as e:
        print(f"Error sending email to {email}: {str(e)}")

@app.post("/api/process")
async def process_message(user_input: UserInput):
    """Process user message and return appropriate response"""
    users = load_users()
    
    # Check if this is a new user
    if user_input.email not in users:
        # Validate email
        try:
            EmailStr._validate(user_input.email)
        except:
            return {"response": "Please enter a valid email address."}
        
        # Create new user
        users[user_input.email] = UserData(email=user_input.email).dict()
        save_users(users)
        return {"response": "Welcome! You're now subscribed to the daily digest at 8:00 AM PST. What would you like to do? (add source/remove source/change time/view sources)"}
    
    # Parse user intent
    intent_data = parse_user_intent(user_input.message, user_input.email)
    intent = intent_data.get("intent")
    user_data = UserData(**users[user_input.email])
    
    if intent == "add_source":
        source = intent_data.get("source")
        if source and source in AVAILABLE_SOURCES:
            if source not in user_data.sources:
                user_data.sources.append(source)
                users[user_input.email] = user_data.dict()
                save_users(users)
                return {"response": f"Added {source} to your sources. Anything else?"}
            return {"response": f"You already have {source} in your sources."}
        return {"response": "Source not recognized. Available: medium, google_news_tech, google_news_business, google_news_world, book_summaries"}
    
    elif intent == "remove_source":
        source = intent_data.get("source")
        if source and source in user_data.sources:
            user_data.sources.remove(source)
            users[user_input.email] = user_data.dict()
            save_users(users)
            return {"response": f"Removed {source} from your sources. Anything else?"}
        return {"response": f"You don't have {source} in your sources."}
    
    elif intent == "change_time":
        time_str = intent_data.get("time")
        if time_str:
            user_data.send_time = time_str
            users[user_input.email] = user_data.dict()
            save_users(users)
            return {"response": f"Changed delivery time to {time_str}. Anything else?"}
        return {"response": "Please specify a valid time (e.g., 09:30)."}
    
    elif intent == "set_timezone":
        timezone = intent_data.get("timezone")
        if timezone:
            try:
                pytz.timezone(timezone)
                user_data.timezone = timezone
                users[user_input.email] = user_data.dict()
                save_users(users)
                return {"response": f"Set timezone to {timezone}. Anything else?"}
            except:
                return {"response": "Invalid timezone. Please use format like 'America/New_York' or 'Europe/London'."}
    
    elif intent == "view_sources":
        sources_list = ", ".join(user_data.sources)
        return {"response": f"Your current sources: {sources_list}. Delivery time: {user_data.send_time} {user_data.timezone}."}
    
    elif intent == "unsubscribe":
        del users[user_input.email]
        save_users(users)
        return {"response": "You've been unsubscribed. Sorry to see you go!"}
    
    else:
        return {"response": "I can help you: add source, remove source, change time, set timezone, view sources, or unsubscribe. What would you like to do?"}

@app.get("/api/test-digest/{email}")
async def test_digest(email: str):
    """Test endpoint to trigger digest immediately"""
    users = load_users()
    if email not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = UserData(**users[email])
    content = create_digest(user_data)
    send_digest(email, content)
    return {"message": "Test digest sent"}

@app.get("/api/cron/send-digests")
async def cron_send_digests():
    """Vercel cron job endpoint to send scheduled digests"""
    # Load all users
    users = load_users()
    
    # Get current time in different timezones
    current_utc = datetime.now(pytz.UTC)
    
    sent_count = 0
    
    for email, user_dict in users.items():
        user_data = UserData(**user_dict)
        
        # Get user's timezone
        user_tz = pytz.timezone(user_data.timezone)
        user_time = current_utc.astimezone(user_tz)
        
        # Check if it's time to send the digest
        send_hour, send_minute = map(int, user_data.send_time.split(':'))
        
        if user_time.hour == send_hour:
            # Create and send digest
            try:
                content = create_digest(user_data)
                send_digest(email, content)
                sent_count += 1
            except Exception as e:
                print(f"Error sending digest to {email}: {str(e)}")
    
    return {
        "message": f"Cron job completed. Sent {sent_count} digests.",
        "timestamp": current_utc.isoformat()
    }

@app.get("/")
async def root():
    return {"message": "News Automation API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 