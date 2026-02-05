"""
YouTube transcript fetching using direct HTTP requests.
Fetches captions directly from YouTube's timedtext API.
Falls back to scraping if needed.
"""

import os
import re
import json
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

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


def _clean_text(text: str) -> str:
    """Clean a transcript text segment."""
    # Remove music/applause markers
    text = re.sub(r'\[.*?(Music|music|MUSIC|♪|♫).*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(Applause|applause|APPLAUSE).*?\]', '', text, flags=re.IGNORECASE)
    # Decode HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&#39;', "'").replace('&quot;', '"')
    # Collapse whitespace
    text = ' '.join(text.split())
    return text.strip()


def _extract_captions_from_html(html: str) -> Optional[str]:
    """Extract caption track URL from YouTube page HTML."""
    # Look for captionTracks in the player response
    patterns = [
        r'"captionTracks":\s*(\[.*?\])',
        r'"captions":\s*\{[^}]*"playerCaptionsTracklistRenderer":\s*\{[^}]*"captionTracks":\s*(\[.*?\])',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            try:
                tracks_json = match.group(1)
                # Fix escaping
                tracks_json = tracks_json.replace('\\"', '"').replace('\\/', '/')
                tracks = json.loads(tracks_json)
                
                # Prefer English, then any language
                for lang_code in ['en', 'en-US', 'en-GB', 'a.en']:
                    for track in tracks:
                        if track.get('languageCode', '').startswith(lang_code.split('.')[0]):
                            return track.get('baseUrl')
                
                # Fall back to first available
                if tracks:
                    return tracks[0].get('baseUrl')
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.debug(f"Failed to parse caption tracks: {e}")
                continue
    
    return None


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


async def _fetch_with_httpx(url: str, headers: dict = None) -> str:
    """Fetch URL content using httpx."""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    if headers:
        default_headers.update(headers)
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=default_headers)
        response.raise_for_status()
        return response.text


def _fetch_sync(url: str, headers: dict = None) -> str:
    """Fetch URL content synchronously using httpx."""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    if headers:
        default_headers.update(headers)
    
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=default_headers)
        response.raise_for_status()
        return response.text


def fetch_transcript(
    video_id: str,
    language_hint: Optional[str] = None
) -> TranscriptResult:
    """
    Fetch transcript for a YouTube video using direct HTTP requests.
    
    Args:
        video_id: YouTube video ID
        language_hint: Optional preferred language code
        
    Returns:
        TranscriptResult with segments and detected language
        
    Raises:
        TranscriptNotAvailable: If transcript cannot be fetched
    """
    try:
        # Step 1: Fetch YouTube video page
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        logger.info(f"Fetching video page for {video_id}")
        
        html = _fetch_sync(video_url)
        
        # Step 2: Extract caption track URL
        caption_url = _extract_captions_from_html(html)
        
        if not caption_url:
            # Check if captions are disabled
            if '"playabilityStatus":{"status":"ERROR"' in html:
                raise TranscriptNotAvailable("Video is unavailable or private")
            if 'Sign in to confirm' in html or 'confirm you' in html.lower():
                raise TranscriptNotAvailable("YouTube requires sign-in (bot detection)")
            raise TranscriptNotAvailable("No captions found for this video")
        
        logger.info(f"Found caption URL, fetching captions")
        
        # Step 3: Fetch captions
        captions_xml = _fetch_sync(caption_url)
        
        # Step 4: Parse captions
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
    
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching transcript: {e}")
        raise TranscriptNotAvailable(f"Failed to fetch video: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error fetching transcript: {e}")
        raise TranscriptNotAvailable(f"Network error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript: {e}")
        if "Sign in" in str(e) or "bot" in str(e).lower():
            raise TranscriptNotAvailable("YouTube requires sign-in (bot detection)")
        raise TranscriptNotAvailable(f"Failed to fetch transcript: {e}")


def segments_to_json(segments: List[TranscriptSegment]) -> List[dict]:
    """Convert segments to JSON-serializable format for OpenAI."""
    return [
        {"t": seg.t, "d": seg.d, "text": seg.text}
        for seg in segments
    ]
