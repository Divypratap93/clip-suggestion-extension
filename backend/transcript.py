"""
YouTube transcript fetching and preprocessing.
Uses youtube-transcript-api to fetch captions.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


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
PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]

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


def _select_transcript(video_id: str, language_hint: Optional[str] = None):
    """
    Select the best available transcript.
    
    Priority:
    1. language_hint if provided
    2. English variants (en, en-US, en-GB)
    3. First available transcript
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
        raise TranscriptNotAvailable(f"Cannot access transcript: {e}")
    except Exception as e:
        raise TranscriptNotAvailable(f"Error listing transcripts: {e}")
    
    # Build list of languages to try
    languages_to_try = []
    
    if language_hint:
        languages_to_try.append(language_hint)
    
    languages_to_try.extend(PREFERRED_LANGUAGES)
    
    # Try each language in order
    for lang in languages_to_try:
        try:
            transcript = transcript_list.find_transcript([lang])
            return transcript
        except NoTranscriptFound:
            continue
    
    # Fall back to first available transcript
    try:
        # Get any available transcript
        for transcript in transcript_list:
            return transcript
    except Exception:
        pass
    
    raise TranscriptNotAvailable("No transcript available for this video")


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
    # Select best transcript
    transcript = _select_transcript(video_id, language_hint)
    
    try:
        # Fetch the transcript data
        transcript_data = transcript.fetch()
    except Exception as e:
        raise TranscriptNotAvailable(f"Failed to fetch transcript: {e}")
    
    # Process segments
    segments: List[TranscriptSegment] = []
    
    for item in transcript_data:
        text = _clean_text(item.get('text', ''))
        
        # Skip empty segments
        if not text:
            continue
        
        start = float(item.get('start', 0))
        duration = float(item.get('duration', 0))
        
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
        language=transcript.language_code
    )


def segments_to_json(segments: List[TranscriptSegment]) -> List[dict]:
    """Convert segments to JSON-serializable format for OpenAI."""
    return [
        {"t": seg.t, "d": seg.d, "text": seg.text}
        for seg in segments
    ]
