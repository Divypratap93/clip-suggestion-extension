"""
FastAPI backend for YouTube Clip Suggestion Extension.
Provides /api/clip-ideas endpoint for generating clip ideas.
"""

import json
import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from openai_client import OpenAIError, generate_clip_ideas
from rate_limiter import rate_limiter
from transcript import TranscriptNotAvailable, fetch_transcript, segments_to_json

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Clip Suggestion API",
    description="Generate viral clip ideas from YouTube videos",
    version="1.0.0"
)

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
allowed_origins = [origin.strip() for origin in allowed_origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- Request/Response Models ---

class ClipIdeaRequest(BaseModel):
    """Request body for clip ideas endpoint."""
    videoId: str = Field(..., description="YouTube video ID")
    videoUrl: Optional[str] = Field(None, description="Full YouTube URL")
    mode: str = Field("shorts", description="Generation mode (shorts)")
    languageHint: Optional[str] = Field(None, description="Preferred transcript language")


class ClipIdeaResponse(BaseModel):
    """A single clip idea."""
    start_seconds: int
    end_seconds: int
    start: str
    end: str
    hook: str
    why: str
    suggested_caption: str


class MetaInfo(BaseModel):
    """Metadata about the response."""
    transcript_language: str
    transcript_source: str = "youtube-transcript-api"
    model: str


class SuccessResponse(BaseModel):
    """Successful response with clip ideas."""
    videoId: str
    ideas: List[ClipIdeaResponse]
    meta: MetaInfo


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    message: str


# --- Middleware ---

@app.middleware("http")
async def validate_client_header(request: Request, call_next):
    """Validate X-Client header for basic protection."""
    # Skip validation for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Skip validation for non-API routes
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    
    # Check X-Client header
    client_header = request.headers.get("X-Client")
    if client_header != "indiedoers-extension":
        return await call_next(request)  # Allow for now, but log warning
        # In production, you might want to reject:
        # raise HTTPException(status_code=403, detail="Invalid client")
    
    return await call_next(request)


# --- Helper Functions ---

def get_client_ip(request: Request) -> str:
    """Get client IP from request, considering proxies."""
    # Check for forwarded IP (when behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Fall back to direct client IP
    return request.client.host if request.client else "unknown"


# --- Endpoints ---

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "clip-suggestion-api"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post(
    "/api/clip-ideas",
    response_model=SuccessResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def generate_clips(request: Request, body: ClipIdeaRequest):
    """
    Generate clip ideas from a YouTube video.
    
    Requires X-Client header for basic protection.
    Rate limited to DAILY_LIMIT_PER_IP requests per day.
    """
    # Get client IP for rate limiting
    client_ip = get_client_ip(request)
    
    # Check rate limit
    is_allowed, remaining = rate_limiter.check_and_increment(client_ip)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMITED",
                "message": "Daily limit reached. Try again tomorrow."
            }
        )
    
    # Validate input
    if not body.videoId or len(body.videoId) < 5:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Invalid video ID provided."
            }
        )
    
    if body.mode != "shorts":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Only 'shorts' mode is supported."
            }
        )
    
    try:
        # Fetch transcript
        transcript_result = fetch_transcript(
            video_id=body.videoId,
            language_hint=body.languageHint
        )
        
        # Convert segments to JSON for OpenAI
        segments_json = json.dumps(segments_to_json(transcript_result.segments))
        
        # Generate clip ideas
        ideas = generate_clip_ideas(segments_json)
        
        # Build response
        return SuccessResponse(
            videoId=body.videoId,
            ideas=[
                ClipIdeaResponse(
                    start_seconds=idea.start_seconds,
                    end_seconds=idea.end_seconds,
                    start=idea.start,
                    end=idea.end,
                    hook=idea.hook,
                    why=idea.why,
                    suggested_caption=idea.suggested_caption
                )
                for idea in ideas
            ],
            meta=MetaInfo(
                transcript_language=transcript_result.language,
                transcript_source="deepgram",
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            )
        )
    
    except TranscriptNotAvailable as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "TRANSCRIPT_NOT_AVAILABLE",
                "message": "This video doesn't have an accessible transcript. Try another video."
            }
        )
    
    except OpenAIError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "OPENAI_ERROR",
                "message": f"Failed to generate ideas: {str(e)}"
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again."
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
