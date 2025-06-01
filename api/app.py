import os
import json
import re
from datetime import datetime, time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import openai
from firecrawl import FirecrawlApp
import resend
import pytz
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

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

class UserInput(BaseModel):
    email: str
    message: str

class UserData(BaseModel):
    email: EmailStr
    sources: List[Dict[str, str]] = Field(default_factory=list)  # [{"name": "TechCrunch", "url": "https://techcrunch.com"}]
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

def parse_url_from_text(text: str) -> Optional[str]:
    """Parse a URL from text or convert website name to URL"""
    # Check if it's already a URL
    url_pattern = re.compile(r'https?://[^\s]+')
    url_match = url_pattern.search(text)
    if url_match:
        return url_match.group()
    
    # Try to extract website name and convert to URL
    # Remove common words
    text = text.lower().strip()
    text = re.sub(r'\b(add|remove|website|site|www|com|https?://)\b', '', text).strip()
    
    # If it looks like a domain, add https://
    if '.' in text:
        return f"https://{text}"
    
    # Common website mappings
    common_sites = {
        'techcrunch': 'https://techcrunch.com',
        'verge': 'https://theverge.com',
        'wired': 'https://wired.com',
        'ars technica': 'https://arstechnica.com',
        'hacker news': 'https://news.ycombinator.com',
        'reddit': 'https://reddit.com',
        'medium': 'https://medium.com',
        'dev.to': 'https://dev.to',
        'github': 'https://github.com/trending',
        'product hunt': 'https://producthunt.com',
        'indie hackers': 'https://indiehackers.com',
    }
    
    for name, url in common_sites.items():
        if name in text:
            return url
    
    # Default: assume it's a website name and add .com
    if text:
        return f"https://{text.replace(' ', '')}.com"
    
    return None

def extract_site_name_from_url(url: str) -> str:
    """Extract a readable name from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Remove www. and common TLDs
        domain = re.sub(r'^www\.', '', domain)
        domain = re.sub(r'\.(com|org|net|io|co|dev|ai)$', '', domain)
        # Capitalize first letter
        return domain.capitalize()
    except:
        return url

def parse_user_intent(message: str, email: str) -> Dict:
    """Use OpenAI to parse user intent from natural language"""
    prompt = f"""
    Parse the user's intent from their message. The user email is: {email}
    
    Message: "{message}"
    
    Possible intents:
    - add_source: User wants to add a news source (could be URL or website name)
    - confirm_add_source: User is confirming to add a source (message starts with "confirm add source")
    - remove_source: User wants to remove a news source
    - change_time: User wants to change delivery time (extract time in HH:MM format)
    - set_timezone: User wants to set timezone (extract timezone)
    - set_time_and_timezone: User wants to set both time and timezone (e.g., "5:03 pm pst")
    - unsubscribe: User wants to unsubscribe
    - view_sources: User wants to see their current sources
    - done: User is done with setup (words like "done", "finish", "complete")
    - help: User needs help or the intent is unclear
    
    For time parsing:
    - Convert 12-hour format to 24-hour format (e.g., "5:03 pm" -> "17:03")
    - Recognize timezone abbreviations: PST/PDT -> America/Los_Angeles, EST/EDT -> America/New_York, CST/CDT -> America/Chicago, MST/MDT -> America/Denver
    - If the message contains both time and timezone (e.g., "5:03 pm pst"), set intent as "set_time_and_timezone"
    
    Return a JSON object with:
    - intent: one of the above intents
    - source: the source text if applicable (could be URL or website name)
    - time: the time if applicable (in HH:MM format, 24-hour)
    - timezone: the timezone if applicable (full timezone name, not abbreviation)
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

def scrape_content(source_dict: Dict[str, str]) -> List[Dict]:
    """Scrape content from a source using Firecrawl"""
    try:
        # Scrape the URL
        data = firecrawl_app.scrape_url(
            source_dict["url"],
            params={
                "formats": ["markdown"],
                "onlyMainContent": True
            }
        )
        
        # Extract relevant content using OpenAI
        prompt = f"""
        Extract the most relevant and interesting content from this source: {source_dict["name"]}.
        Focus on recent articles, news, and updates.
        
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
        print(f"Error scraping {source_dict['name']}: {str(e)}")
        return []

def create_digest(user_data: UserData) -> str:
    """Create email digest content"""
    all_content = []
    
    # Add default sources if user has no custom sources
    sources_to_scrape = user_data.sources if user_data.sources else [
        {"name": "Medium AI", "url": "https://medium.com/tag/artificial-intelligence"},
        {"name": "TechCrunch", "url": "https://techcrunch.com"}
    ]
    
    # Scrape content from each source
    for source in sources_to_scrape:
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
    - Dark mode friendly colors
    
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
        # Use actual email address
        resend.Emails.send({
            "from": "News Digest <onboarding@resend.dev>",  # Using Resend's test email
            "to": email,
            "subject": f"Your Daily News Digest - {datetime.now().strftime('%B %d, %Y')}",
            "html": content
        })
        print(f"Email sent successfully to {email}")
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
        users[user_input.email] = UserData(email=user_input.email).model_dump()
        save_users(users)
        return {"response": "Welcome! You're now subscribed to the daily digest."}
    
    # Parse user intent
    intent_data = parse_user_intent(user_input.message, user_input.email)
    intent = intent_data.get("intent")
    user_data = UserData(**users[user_input.email])
    
    if intent == "add_source":
        source_text = intent_data.get("source", user_input.message)
        # Try to parse URL from the text
        url = parse_url_from_text(source_text)
        if url:
            return {"response": f"Is this the correct URL: {url}?", "confirmUrl": url}
        return {"response": "Could not parse URL. Please provide a valid URL or website name."}
    
    elif intent == "confirm_add_source":
        # Extract URL from confirmation message
        url_match = re.search(r'https?://[^\s]+', user_input.message)
        if url_match:
            url = url_match.group()
            name = extract_site_name_from_url(url)
            
            # Check if already exists
            existing = any(s["url"] == url for s in user_data.sources)
            if not existing:
                user_data.sources.append({"name": name, "url": url})
                users[user_input.email] = user_data.model_dump()
                save_users(users)
                return {"response": f"Added {name} to your sources. Add another or say 'done'."}
            return {"response": f"You already have {name} in your sources."}
        return {"response": "Could not find URL to add."}
    
    elif intent == "remove_source":
        source_text = intent_data.get("source", "").lower()
        removed = False
        for i, source in enumerate(user_data.sources):
            if source_text in source["name"].lower() or source_text in source["url"].lower():
                removed_source = user_data.sources.pop(i)
                users[user_input.email] = user_data.model_dump()
                save_users(users)
                return {"response": f"Removed {removed_source['name']} from your sources."}
        return {"response": "Source not found in your list."}
    
    elif intent == "change_time":
        time_str = intent_data.get("time")
        if time_str:
            user_data.send_time = time_str
            users[user_input.email] = user_data.model_dump()
            save_users(users)
            return {"response": f"Changed delivery time to {time_str}."}
        return {"response": "Please specify a valid time (e.g., 09:30)."}
    
    elif intent == "set_timezone":
        timezone = intent_data.get("timezone")
        if timezone:
            try:
                pytz.timezone(timezone)
                user_data.timezone = timezone
                users[user_input.email] = user_data.model_dump()
                save_users(users)
                return {"response": f"Set timezone to {timezone}."}
            except:
                return {"response": "Invalid timezone. Please use format like 'America/New_York' or 'Europe/London'."}
    
    elif intent == "set_time_and_timezone":
        time_str = intent_data.get("time")
        timezone = intent_data.get("timezone")
        if time_str and timezone:
            try:
                pytz.timezone(timezone)
                user_data.send_time = time_str
                user_data.timezone = timezone
                users[user_input.email] = user_data.model_dump()
                save_users(users)
                return {"response": f"Perfect! I'll send your digest at {time_str} {timezone}."}
            except:
                return {"response": "Invalid timezone. Please try again with a valid timezone."}
        return {"response": "Please specify both time and timezone (e.g., '5:03 pm pst')."}
    
    elif intent == "view_sources":
        if user_data.sources:
            sources_list = ", ".join([s["name"] for s in user_data.sources])
            return {"response": f"Your sources: {sources_list}. Delivery: {user_data.send_time} {user_data.timezone}."}
        return {"response": f"No custom sources. Using default sources. Delivery: {user_data.send_time} {user_data.timezone}."}
    
    elif intent == "done":
        return {"response": "Setup complete! Your digests will be sent at the scheduled time."}
    
    elif intent == "unsubscribe":
        del users[user_input.email]
        save_users(users)
        return {"response": "You've been unsubscribed. Sorry to see you go!"}
    
    else:
        return {"response": "I can help you: add source, remove source, change time, set timezone, view sources, or say 'done' when finished."}

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
        
        # Check if it's time to send the digest (exact minute match)
        send_hour, send_minute = map(int, user_data.send_time.split(':'))
        
        if user_time.hour == send_hour and user_time.minute == send_minute:
            # Create and send digest
            try:
                content = create_digest(user_data)
                send_digest(email, content)
                sent_count += 1
                print(f"Sent digest to {email} at {user_time}")
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