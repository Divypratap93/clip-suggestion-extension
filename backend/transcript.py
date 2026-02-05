"""
YouTube transcript fetching using Deepgram.
Downloads audio from YouTube and transcribes using Deepgram's API.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from deepgram import DeepgramClient


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


# Maximum segments to process
MAX_SEGMENTS = 2000

# Patterns to remove from transcript
MUSIC_PATTERN = re.compile(r'\[.*?(Music|music|MUSIC|♪|♫).*?\]', re.IGNORECASE)
APPLAUSE_PATTERN = re.compile(r'\[.*?(Applause|applause|APPLAUSE).*?\]', re.IGNORECASE)


def _clean_text(text: str) -> str:
    """Clean a transcript text segment."""
    text = MUSIC_PATTERN.sub('', text)
    text = APPLAUSE_PATTERN.sub('', text)
    text = ' '.join(text.split())
    return text.strip()


def _get_youtube_audio_url(video_id: str) -> str:
    """Get direct audio URL from YouTube using yt-dlp."""
    try:
        result = subprocess.run(
            [
                'yt-dlp',
                '-f', 'bestaudio',
                '-g',  # Get URL only
                '--no-warnings',
                f'https://www.youtube.com/watch?v={video_id}'
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise TranscriptNotAvailable(f"Failed to get audio URL: {result.stderr}")
        
        audio_url = result.stdout.strip()
        if not audio_url:
            raise TranscriptNotAvailable("No audio URL returned")
        
        return audio_url
    except subprocess.TimeoutExpired:
        raise TranscriptNotAvailable("Timeout getting audio URL")
    except FileNotFoundError:
        raise TranscriptNotAvailable("yt-dlp not installed")


def _transcribe_with_deepgram(audio_url: str) -> TranscriptResult:
    """Transcribe audio using Deepgram API."""
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise TranscriptNotAvailable("DEEPGRAM_API_KEY not configured")
    
    try:
        client = DeepgramClient(api_key)
        
        # Use the listen.prerecorded method with options dict
        options = {
            "model": "nova-2",
            "language": "en",
            "smart_format": True,
            "punctuate": True,
            "paragraphs": True,
            "utterances": True,
            "diarize": False,
        }
        
        # Transcribe from URL
        response = client.listen.rest.v("1").transcribe_url(
            {"url": audio_url},
            options
        )
        
        # Extract segments from utterances
        segments: List[TranscriptSegment] = []
        
        # Try to get utterances first (better segmentation)
        utterances = None
        if hasattr(response, 'results') and hasattr(response.results, 'utterances'):
            utterances = response.results.utterances
        
        if utterances:
            for utterance in utterances:
                text = _clean_text(utterance.transcript)
                if not text:
                    continue
                
                start = float(utterance.start)
                end = float(utterance.end)
                duration = end - start
                
                segments.append(TranscriptSegment(
                    t=round(start, 2),
                    d=round(duration, 2),
                    text=text
                ))
        else:
            # Fall back to words if no utterances
            channels = response.results.channels if hasattr(response.results, 'channels') else None
            if channels and len(channels) > 0:
                alternatives = channels[0].alternatives
                if alternatives and len(alternatives) > 0:
                    words = alternatives[0].words if hasattr(alternatives[0], 'words') else []
                    
                    # Group words into ~5 second chunks
                    current_segment_words = []
                    segment_start = 0.0
                    
                    for word in words:
                        word_text = word.word if hasattr(word, 'word') else str(word)
                        word_start = float(word.start) if hasattr(word, 'start') else 0
                        word_end = float(word.end) if hasattr(word, 'end') else 0
                        
                        if not current_segment_words:
                            segment_start = word_start
                        
                        current_segment_words.append(word_text)
                        
                        # Create segment every ~5 seconds or at sentence end
                        if word_end - segment_start >= 5.0 or word_text.endswith(('.', '?', '!')):
                            text = _clean_text(' '.join(current_segment_words))
                            if text:
                                segments.append(TranscriptSegment(
                                    t=round(segment_start, 2),
                                    d=round(word_end - segment_start, 2),
                                    text=text
                                ))
                            current_segment_words = []
                    
                    # Add remaining words
                    if current_segment_words and words:
                        text = _clean_text(' '.join(current_segment_words))
                        if text:
                            last_word = words[-1]
                            last_end = float(last_word.end) if hasattr(last_word, 'end') else 0
                            segments.append(TranscriptSegment(
                                t=round(segment_start, 2),
                                d=round(last_end - segment_start, 2),
                                text=text
                            ))
        
        if not segments:
            raise TranscriptNotAvailable("No transcript content from Deepgram")
        
        # Limit segments
        if len(segments) > MAX_SEGMENTS:
            segments = segments[:MAX_SEGMENTS]
        
        return TranscriptResult(
            segments=segments,
            language="en"
        )
    
    except TranscriptNotAvailable:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
            raise TranscriptNotAvailable("Invalid Deepgram API key")
        elif "rate limit" in error_msg or "429" in error_msg:
            raise TranscriptNotAvailable("Deepgram rate limit exceeded")
        else:
            raise TranscriptNotAvailable(f"Deepgram transcription failed: {e}")


def fetch_transcript(
    video_id: str,
    language_hint: Optional[str] = None
) -> TranscriptResult:
    """
    Fetch transcript for a YouTube video using Deepgram.
    
    Args:
        video_id: YouTube video ID
        language_hint: Optional preferred language code (not used with Deepgram)
        
    Returns:
        TranscriptResult with segments and detected language
        
    Raises:
        TranscriptNotAvailable: If transcript cannot be fetched
    """
    # Step 1: Get audio URL from YouTube
    audio_url = _get_youtube_audio_url(video_id)
    
    # Step 2: Transcribe with Deepgram
    return _transcribe_with_deepgram(audio_url)


def segments_to_json(segments: List[TranscriptSegment]) -> List[dict]:
    """Convert segments to JSON-serializable format for OpenAI."""
    return [
        {"t": seg.t, "d": seg.d, "text": seg.text}
        for seg in segments
    ]
