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
    
    # Create API instance (new in v1.2.4)
    api = YouTubeTranscriptApi()
    
    try:
        # Try to fetch transcript with preferred languages
        transcript = api.fetch(video_id, languages=languages)
    except Exception as e:
        # Try to fetch any available transcript
        try:
            transcript_list = api.list(video_id)
            # Get first available transcript
            for t in transcript_list:
                transcript = t.fetch()
                break
            else:
                raise TranscriptNotAvailable("No transcripts available")
        except Exception as inner_e:
            error_msg = str(e).lower()
            if "disabled" in error_msg:
                raise TranscriptNotAvailable("Transcripts are disabled for this video")
            elif "no transcript" in error_msg or "could not" in error_msg:
                raise TranscriptNotAvailable("No transcript found for this video")
            else:
                raise TranscriptNotAvailable(f"Cannot fetch transcript: {e}")
    
    # Process segments
    segments: List[TranscriptSegment] = []
    
    # The new API returns a FetchedTranscript which is iterable
    for snippet in transcript:
        text = _clean_text(snippet.text)
        
        # Skip empty segments
        if not text:
            continue
        
        segments.append(TranscriptSegment(
            t=round(snippet.start, 2),
            d=round(snippet.duration, 2),
            text=text
        ))
    
    # Limit segments to avoid huge token counts
    if len(segments) > MAX_SEGMENTS:
        segments = segments[:MAX_SEGMENTS]
    
    if not segments:
        raise TranscriptNotAvailable("Transcript is empty after processing")
    
    # Get language from transcript if available
    detected_language = getattr(transcript, 'language_code', 'en') or 'en'
    
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
