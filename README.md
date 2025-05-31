# News Automation Agent

An AI-powered news digest service that automatically crawls Medium, Google News, and book summary sites to deliver personalized daily email digests. Features a minimalist UI with just one text input that uses OpenAI to understand natural language commands.

## Features

- 🤖 **AI-Powered Interface**: Single text input that understands natural language
- 📰 **Multiple Sources**: Crawls Medium (AI/productivity), Google News (tech/business/world), and book summaries
- 📧 **Daily Email Digests**: Automated emails with bullet-point summaries
- 🌍 **Timezone Support**: Set your preferred delivery time and timezone
- 🎯 **Customizable**: Add/remove sources, change delivery times
- 🚀 **Serverless**: Runs on Vercel with automatic scaling

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/anishkganesh/news-automation-agent.git
cd news-automation-agent
pip install -r requirements.txt
```

### 2. Set Up API Keys

Create a `.env` file:

```bash
OPENAI_API_KEY=your_openai_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
RESEND_API_KEY=your_resend_api_key  # Optional for email sending
```

**Get your API keys:**
- OpenAI: https://platform.openai.com/api-keys
- Firecrawl: https://firecrawl.dev
- Resend: https://resend.com (free tier available)

### 3. Local Development

```bash
python api/app.py
```

Open `index.html` in your browser or serve it locally.

### 4. Deploy to Vercel

1. Install Vercel CLI: `npm i -g vercel`
2. Set up environment variables in Vercel:
   ```bash
   vercel env add OPENAI_API_KEY
   vercel env add FIRECRAWL_API_KEY
   vercel env add RESEND_API_KEY
   ```
3. Deploy:
   ```bash
   vercel
   ```

## Usage

1. **First Visit**: Enter your email address
2. **Commands**: Use natural language like:
   - "add medium" or "subscribe to medium articles"
   - "remove google news tech" 
   - "change time to 9:00 AM"
   - "set timezone to America/New_York"
   - "view my sources"
   - "unsubscribe"

## Architecture

- **Frontend**: Single HTML file with React (no build step)
- **Backend**: FastAPI (2 Python files)
- **Storage**: JSON file (upgradeable to database)
- **Email**: Resend API
- **Scraping**: Firecrawl API
- **AI**: OpenAI GPT-3.5

## Available Sources

- `medium`: AI and productivity articles from Medium
- `google_news_tech`: Technology news from Google News
- `google_news_business`: Business news from Google News
- `google_news_world`: World news from Google News
- `book_summaries`: Self-help book summaries and quotes

## API Endpoints

- `POST /api/process`: Process user commands
- `GET /api/test-digest/{email}`: Send test digest immediately
- `GET /api/cron/send-digests`: Cron endpoint for scheduled sends

## Email Setup with Resend

1. Sign up at [resend.com](https://resend.com)
2. Verify your domain or use their test domain
3. Get your API key from the dashboard
4. Add it to your environment variables

## Customization

### Adding New Sources

Edit `AVAILABLE_SOURCES` in `api/app.py`:

```python
"source_name": {
    "url": "https://example.com", 
    "topics": ["topic1", "topic2"]
}
```

### Modifying Email Template

Update the `create_digest()` function in `api/app.py` to customize the email format.

## Environment Variables

- `OPENAI_API_KEY`: Required for AI parsing and content formatting
- `FIRECRAWL_API_KEY`: Required for web scraping
- `RESEND_API_KEY`: Required for sending emails (get free at resend.com)

## Notes

- The cron job runs every hour and checks which users need their digest sent
- User data is stored in `users.json` (gitignored for privacy)
- For production, consider using a proper database instead of JSON file

## License

MIT 