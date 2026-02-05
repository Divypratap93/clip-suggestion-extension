"""
Validation logic for clip ideas.
Ensures clips meet duration and format requirements.
"""

from typing import List, Optional, Tuple
from pydantic import BaseModel


class ClipIdea(BaseModel):
    """A validated clip idea."""
    start_seconds: int
    end_seconds: int
    start: str  # mm:ss format
    end: str    # mm:ss format
    hook: str
    why: str
    suggested_caption: str


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


# Clip duration constraints
MIN_CLIP_DURATION = 25  # seconds
MAX_CLIP_DURATION = 70  # seconds


def seconds_to_mmss(seconds: int) -> str:
    """Convert seconds to mm:ss format."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def validate_clip_idea(idea: dict) -> Optional[ClipIdea]:
    """
    Validate a single clip idea from OpenAI response.
    
    Returns:
        ClipIdea if valid, None if invalid
    """
    try:
        start_seconds = int(idea.get('start_seconds', 0))
        end_seconds = int(idea.get('end_seconds', 0))
        
        # Check start < end
        if start_seconds >= end_seconds:
            return None
        
        # Check valid timestamps
        if start_seconds < 0:
            return None
        
        # Check duration constraints
        duration = end_seconds - start_seconds
        if duration < MIN_CLIP_DURATION or duration > MAX_CLIP_DURATION:
            return None
        
        # Get text fields
        hook = str(idea.get('hook', '')).strip()
        why = str(idea.get('why', '')).strip()
        suggested_caption = str(idea.get('suggested_caption', '')).strip()
        
        # Require at least hook and why
        if not hook or not why:
            return None
        
        return ClipIdea(
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            start=seconds_to_mmss(start_seconds),
            end=seconds_to_mmss(end_seconds),
            hook=hook,
            why=why,
            suggested_caption=suggested_caption
        )
    except (ValueError, TypeError):
        return None


def validate_ideas(raw_ideas: List[dict]) -> Tuple[List[ClipIdea], bool]:
    """
    Validate a list of clip ideas.
    
    Returns:
        Tuple of (valid_ideas, needs_regeneration)
        needs_regeneration is True if we don't have exactly 5 valid ideas
    """
    valid_ideas: List[ClipIdea] = []
    
    for idea in raw_ideas:
        validated = validate_clip_idea(idea)
        if validated:
            valid_ideas.append(validated)
    
    # We need exactly 5 ideas
    needs_regeneration = len(valid_ideas) != 5
    
    # If we have more than 5, take first 5
    if len(valid_ideas) > 5:
        valid_ideas = valid_ideas[:5]
        needs_regeneration = False
    
    return valid_ideas, needs_regeneration
