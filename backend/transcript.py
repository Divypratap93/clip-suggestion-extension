"""
YouTube transcript fetching using YouTube's Innertube API.
This is the internal API that YouTube's web client uses.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


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

# YouTube Innertube API constants
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
INNERTUBE_CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20240101.00.00",
    "hl": "en",
    "gl": "US",
}


def _clean_text(text: str) -> str:
    """Clean a transcript text segment."""
    # Remove music/applause markers
    text = re.sub(r'\[.*?(Music|music|MUSIC|♪|♫).*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(Applause|applause|APPLAUSE).*?\]', '', text, flags=re.IGNORECASE)
    # Decode HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&#39;', "'").replace('&quot;', '"')
    text = text.replace('\n', ' ')
    # Collapse whitespace
    text = ' '.join(text.split())
    return text.strip()


def _parse_xml_captions(xml_content: str) -> List[TranscriptSegment]:
    """Parse YouTube's XML caption format."""
    segments = []
    
    try:
        root = ET.fromstring(xml_content)
        
        for text_elem in root.findall('.//text'):
            start = float(text_elem.get('start', 0))
            duration = float(text_elem.get('dur', 0))
            text = _clean_text(text_elem.text or '')
            
            if text:
                segments.append(TranscriptSegment(
                    t=round(start, 2),
                    d=round(duration, 2),
                    text=text
                ))
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML captions: {e}")
    
    return segments


def _get_captions_via_innertube(video_id: str) -> Optional[str]:
    """
    Get caption URL using YouTube's Innertube API.
    This is the same API that YouTube's web player uses.
    """
    innertube_url = f"https://www.youtube.com/youtubei/v1/player?key={INNERTUBE_API_KEY}"
    
    payload = {
        "context": {
            "client": INNERTUBE_CLIENT
        },
        "videoId": video_id
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.youtube.com",
        "Referer": f"https://www.youtube.com/watch?v={video_id}",
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(innertube_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # Check playability status
        playability = data.get('playabilityStatus', {})
        if playability.get('status') == 'ERROR':
            reason = playability.get('reason', 'Unknown error')
            logger.warning(f"Video not playable: {reason}")
            raise TranscriptNotAvailable(f"Video not available: {reason}")
        
        if playability.get('status') == 'LOGIN_REQUIRED':
            logger.warning("Video requires login")
            raise TranscriptNotAvailable("Video requires sign-in")
        
        # Extract caption tracks
        captions = data.get('captions', {})
        renderer = captions.get('playerCaptionsTracklistRenderer', {})
        tracks = renderer.get('captionTracks', [])
        
        if not tracks:
            logger.info("No caption tracks found in Innertube response")
            return None
        
        # Prefer English captions
        for track in tracks:
            lang = track.get('languageCode', '')
            if lang.startswith('en'):
                base_url = track.get('baseUrl', '')
                if base_url:
                    logger.info(f"Found English caption track via Innertube: {lang}")
                    return base_url
        
        # Fall back to first available
        base_url = tracks[0].get('baseUrl', '')
        if base_url:
            logger.info(f"Using first caption track: {tracks[0].get('languageCode', 'unknown')}")
            return base_url
        
        return None
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Innertube API HTTP error: {e.response.status_code}")
        if e.response.status_code == 429:
            raise TranscriptNotAvailable("Rate limited by YouTube")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Innertube response: {e}")
        return None


def fetch_transcript(
    video_id: str,
    language_hint: Optional[str] = None
) -> TranscriptResult:
    """
    Fetch transcript for a YouTube video using Innertube API.
    
    Args:
        video_id: YouTube video ID
        language_hint: Optional preferred language code
        
    Returns:
        TranscriptResult with segments and detected language
        
    Raises:
        TranscriptNotAvailable: If transcript cannot be fetched
    """
    try:
        # Step 1: Get caption URL via Innertube API
        logger.info(f"Fetching captions for video {video_id} via Innertube API")
        
        caption_url = _get_captions_via_innertube(video_id)
        
        if not caption_url:
            raise TranscriptNotAvailable("No captions available for this video")
        
        # Step 2: Fetch the actual captions
        logger.info("Fetching caption content")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(caption_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response.raise_for_status()
            captions_xml = response.text
        
        # Step 3: Parse captions
        segments = _parse_xml_captions(captions_xml)
        
        if not segments:
            raise TranscriptNotAvailable("No caption content found")
        
        # Limit segments
        if len(segments) > MAX_SEGMENTS:
            segments = segments[:MAX_SEGMENTS]
        
        logger.info(f"Successfully fetched {len(segments)} caption segments")
        
        return TranscriptResult(
            segments=segments,
            language=language_hint or "en"
        )
    
    except TranscriptNotAvailable:
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching transcript: {e}")
        raise TranscriptNotAvailable(f"Failed to fetch captions: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error fetching transcript: {e}")
        raise TranscriptNotAvailable(f"Network error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript: {e}")
        raise TranscriptNotAvailable(f"Failed to fetch transcript: {e}")


def segments_to_json(segments: List[TranscriptSegment]) -> List[dict]:
    """Convert segments to JSON-serializable format for OpenAI."""
    return [
        {"t": seg.t, "d": seg.d, "text": seg.text}
        for seg in segments
    ]
