# Clip Suggestion API - Backend

FastAPI backend for the YouTube Clip Suggestion Chrome Extension.

## Features

- Fetches YouTube transcripts using `youtube-transcript-api`
- Generates 5 viral clip ideas using OpenAI GPT
- Validates clip durations (25-70 seconds)
- In-memory rate limiting (20 requests/day/IP)
- CORS protection for Chrome extension

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and add your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4.1-mini
ALLOWED_ORIGINS=chrome-extension://YOUR_EXTENSION_ID,http://localhost:3000
DAILY_LIMIT_PER_IP=20
```

### 3. Run the Server

```bash
uvicorn main:app --reload
```

The server will start at `http://localhost:8000`.

## API Endpoints

### Health Check

```bash
GET /
GET /health
```

### Generate Clip Ideas

```bash
POST /api/clip-ideas
Content-Type: application/json
X-Client: indiedoers-extension

{
  "videoId": "dQw4w9WgXcQ",
  "videoUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "mode": "shorts",
  "languageHint": "en"
}
```

#### Success Response

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
    "transcript_source": "youtube-transcript-api",
    "model": "gpt-4.1-mini"
  }
}
```

#### Error Responses

| Code | Error | Description |
|------|-------|-------------|
| 400 | `TRANSCRIPT_NOT_AVAILABLE` | Video has no accessible transcript |
| 400 | `INVALID_INPUT` | Invalid request parameters |
| 429 | `RATE_LIMITED` | Daily limit exceeded |
| 500 | `OPENAI_ERROR` | OpenAI API error |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

## Deployment

### Render / Railway (Recommended for MVP)

1. Push to GitHub
2. Connect repository to Render/Railway
3. Set environment variables in dashboard
4. Deploy

### Docker (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## File Structure

```
backend/
├── main.py           # FastAPI application
├── transcript.py     # YouTube transcript fetching
├── openai_client.py  # OpenAI integration
├── validators.py     # Response validation
├── rate_limiter.py   # In-memory rate limiting
├── requirements.txt  # Python dependencies
├── .env.example      # Environment template
└── README.md         # This file
```
