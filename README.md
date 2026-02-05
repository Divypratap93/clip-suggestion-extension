# Clip Suggestion Extension

A Chrome extension that generates AI-powered viral clip ideas from YouTube videos. Get 5 optimized clip suggestions with timestamps, hooks, and captions in seconds.

![Extension Preview](extension/icons/icon128.png)

## Features

- 🎬 **Smart Clip Detection** - AI analyzes transcripts to find the best moments
- ⏱️ **Precise Timestamps** - Each clip is 25-70 seconds, perfect for Shorts
- 📝 **Hook & Caption** - Get suggested hooks and captions for each clip
- 📋 **One-Click Copy** - Copy formatted clip info to clipboard
- 🌙 **Modern Dark UI** - Beautiful, YouTube-inspired design

## Project Structure

```
Clip-suggestion-extension/
├── backend/              # FastAPI backend
│   ├── main.py          # API server
│   ├── transcript.py    # YouTube transcript fetching
│   ├── openai_client.py # OpenAI integration
│   ├── validators.py    # Response validation
│   ├── rate_limiter.py  # Rate limiting
│   └── requirements.txt # Dependencies
│
├── extension/           # Chrome extension
│   ├── manifest.json    # Extension config
│   ├── popup.html       # Popup UI
│   ├── popup.js         # Extension logic
│   ├── styles.css       # Styling
│   └── icons/           # Extension icons
│
└── README.md            # This file
```

## Quick Start

### 1. Setup Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# Start server
uvicorn main:app --reload
```

### 2. Load Extension

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` folder

### 3. Use the Extension

1. Go to any YouTube video with captions
2. Click the extension icon
3. Click **Generate Clip Ideas**
4. Get 5 AI-powered clip suggestions!

## Configuration

### Backend Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | Required |
| `OPENAI_MODEL` | Model to use | `gpt-4.1-mini` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:3000` |
| `DAILY_LIMIT_PER_IP` | Rate limit per IP/day | `20` |

### Extension Configuration

Update the `API_URL` in `extension/popup.js` to point to your deployed backend:

```javascript
const CONFIG = {
  API_URL: 'https://your-api.com/api/clip-ideas',
  CLIENT_HEADER: 'indiedoers-extension'
};
```

## API Reference

### POST /api/clip-ideas

Generate clip ideas from a YouTube video.

**Request:**
```json
{
  "videoId": "dQw4w9WgXcQ",
  "mode": "shorts",
  "languageHint": "en"
}
```

**Response:**
```json
{
  "videoId": "dQw4w9WgXcQ",
  "ideas": [
    {
      "start_seconds": 192,
      "end_seconds": 238,
      "start": "03:12",
      "end": "03:58",
      "hook": "The moment everything changed...",
      "why": "Strong emotional beat with clear takeaway",
      "suggested_caption": "This was the turning point 🎯"
    }
  ],
  "meta": {
    "transcript_language": "en",
    "model": "gpt-4.1-mini"
  }
}
```

## Deployment

### Backend (Render/Railway)

1. Push to GitHub
2. Connect to Render or Railway
3. Add environment variables
4. Deploy!

### Extension (Chrome Web Store)

1. Update `API_URL` in popup.js
2. Zip the `extension/` folder
3. Upload to Chrome Web Store Developer Dashboard

## Limitations

- **Requires Captions**: Videos must have YouTube captions (auto or manual)
- **Rate Limited**: 20 requests per day per IP (MVP)
- **English Focus**: Works best with English content, but supports other languages

## License

MIT
