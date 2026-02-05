"""
YouTube transcript fetching and preprocessing.
Uses youtube-transcript-api to fetch captions.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from youtube_transcript_api import YouTubeTranscriptApi


class TranscriptNotAvailable(Exception):
    """Raised when transcript cannot be fetched."""
    pass


@dataclass
class TranscriptSegment:
    """A single transcript segment with timing."""
    t: float  # start time in seconds
    d: float  # duration in seconds
    text: str


@dataclass
class TranscriptResult:
    """Result of transcript fetching."""
    segments: List[TranscriptSegment]
    language: str


# Language priority for transcript selection
PREFERRED_LANGUAGES = ["en", "en-US", "en-GB", "en-AU", "en-CA"]

# Maximum segments to process (roughly 25 minutes of content)
MAX_SEGMENTS = 2000

# Patterns to remove from transcript
MUSIC_PATTERN = re.compile(r'\[.*?(Music|music|MUSIC|♪|♫).*?\]', re.IGNORECASE)
APPLAUSE_PATTERN = re.compile(r'\[.*?(Applause|applause|APPLAUSE).*?\]', re.IGNORECASE)


def _clean_text(text: str) -> str:
    """Clean a transcript text segment."""
    # Remove music/applause markers
    text = MUSIC_PATTERN.sub('', text)
    text = APPLAUSE_PATTERN.sub('', text)
    
    # Collapse whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def fetch_transcript(
    video_id: str,
    language_hint: Optional[str] = None
) -> TranscriptResult:
    """
    Fetch and preprocess transcript for a YouTube video.
    
    Args:
        video_id: YouTube video ID
        language_hint: Optional preferred language code
        
    Returns:
        TranscriptResult with segments and detected language
        
    Raises:
        TranscriptNotAvailable: If transcript cannot be fetched
    """
    # Build language priority list
    languages = []
    if language_hint:
        languages.append(language_hint)
    languages.extend(PREFERRED_LANGUAGES)
    
    transcript_data = None
    detected_language = "en"
    
    try:
        # Try to get transcript with preferred languages first
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=languages
            )
            detected_language = language_hint or "en"
        except Exception:
            # Fall back to any available transcript
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            detected_language = "auto"
    except Exception as e:
        error_msg = str(e).lower()
        if "disabled" in error_msg:
            raise TranscriptNotAvailable("Transcripts are disabled for this video")
        elif "no transcript" in error_msg or "could not retrieve" in error_msg:
            raise TranscriptNotAvailable("No transcript found for this video")
        elif "unavailable" in error_msg or "not available" in error_msg:
            raise TranscriptNotAvailable("Video is unavailable or private")
        else:
            raise TranscriptNotAvailable(f"Cannot fetch transcript: {e}")
    
    if not transcript_data:
        raise TranscriptNotAvailable("No transcript data received")
    
    # Process segments
    segments: List[TranscriptSegment] = []
    
    for item in transcript_data:
        # Handle both dict format and object format
        if isinstance(item, dict):
            text = _clean_text(item.get('text', ''))
            start = float(item.get('start', 0))
            duration = float(item.get('duration', 0))
        else:
            # Object format (newer API versions)
            text = _clean_text(getattr(item, 'text', ''))
            start = float(getattr(item, 'start', 0))
            duration = float(getattr(item, 'duration', 0))
        
        # Skip empty segments
        if not text:
            continue
        
        segments.append(TranscriptSegment(
            t=round(start, 2),
            d=round(duration, 2),
            text=text
        ))
    
    # Limit segments to avoid huge token counts
    if len(segments) > MAX_SEGMENTS:
        segments = segments[:MAX_SEGMENTS]
    
    if not segments:
        raise TranscriptNotAvailable("Transcript is empty after processing")
    
    return TranscriptResult(
        segments=segments,
        language=detected_language
    )


def segments_to_json(segments: List[TranscriptSegment]) -> List[dict]:
    """Convert segments to JSON-serializable format for OpenAI."""
    return [
        {"t": seg.t, "d": seg.d, "text": seg.text}
        for seg in segments
    ]
