# Deployment Instructions

## ✅ Local Testing - SUCCESSFUL!

Your news automation agent is now working locally! The test showed:
- ✓ API is running
- ✓ User signup works
- ✓ Adding sources works
- ✓ Viewing sources works
- ✓ Changing delivery time works
- ✓ Email digest generation works

## 🚀 Deploy to Vercel

1. **Install Vercel CLI** (if not already installed):
   ```bash
   npm install -g vercel
   ```

2. **Deploy to Vercel**:
   ```bash
   vercel
   ```
   - Choose the current directory
   - Link to existing project or create new
   - Use default settings

3. **Set Environment Variables in Vercel**:
   ```bash
   vercel env add OPENAI_API_KEY production
   # Paste your OpenAI API key

   vercel env add FIRECRAWL_API_KEY production
   # Paste your Firecrawl API key

   vercel env add RESEND_API_KEY production
   # Paste your Resend API key
   ```

4. **Deploy with environment variables**:
   ```bash
   vercel --prod
   ```

## 📧 Email Configuration

For emails to actually send, you need to:

1. Go to [resend.com](https://resend.com) dashboard
2. Either:
   - Add and verify your own domain, OR
   - Use their test email `onboarding@resend.dev`
3. Update the "from" email in `api/app.py` line 188 if using your own domain

## 🎉 That's it!

Your app will be live at the URL Vercel provides (e.g., `https://news-automation-agent.vercel.app`)

The cron job will run every hour and send digests to users at their scheduled times. 