"""
OpenAI integration for generating clip ideas.
Uses strict JSON output prompting.
"""

import json
import os
from typing import List, Optional

from openai import OpenAI

from validators import ClipIdea, validate_ideas


class OpenAIError(Exception):
    """Raised when OpenAI API call fails."""
    pass


# System prompt for the AI
SYSTEM_PROMPT = """You are a senior video editor and viral clip strategist. You output strict JSON only."""

# User prompt template
USER_PROMPT_TEMPLATE = """You will receive a YouTube transcript with timestamps.
Generate EXACTLY 5 clip ideas for short-form content.

Rules:
- Output MUST be valid JSON only. No markdown. No extra text.
- Each idea must use timestamps that exist in the transcript.
- Each clip duration must be between 25 and 70 seconds.
- Prefer moments with: strong opinions, surprising statements, clear takeaways, emotional beats, punchy stories.
- Avoid greetings, ads, sponsor segments, and housekeeping.
- If language is non-English, still write hook/why/caption in English.

Output schema:
{{
  "ideas": [
    {{
      "start_seconds": number,
      "end_seconds": number,
      "hook": string,
      "why": string,
      "suggested_caption": string
    }}
  ]
}}

Transcript segments (JSON array, each item has t=start seconds, d=duration seconds, text):
{segments_json}"""

# Retry prompt for invalid JSON
RETRY_PROMPT = """Your previous response was not valid JSON or didn't match the schema.
Fix the output to valid JSON matching this exact schema:
{{
  "ideas": [
    {{
      "start_seconds": number,
      "end_seconds": number,
      "hook": string,
      "why": string,
      "suggested_caption": string
    }}
  ]
}}

Return ONLY valid JSON. No markdown code blocks. No extra text."""


def _get_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


def _get_model() -> str:
    """Get model name from environment or default."""
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _parse_response(content: str) -> dict:
    """Parse JSON response from OpenAI."""
    # Strip markdown code blocks if present
    content = content.strip()
    if content.startswith("```"):
        # Remove first line (```json or ```)
        lines = content.split('\n')
        content = '\n'.join(lines[1:])
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OpenAIError(f"Invalid JSON response: {e}")


def generate_clip_ideas(
    segments_json: str,
    max_retries: int = 1
) -> List[ClipIdea]:
    """
    Generate clip ideas using OpenAI.
    
    Args:
        segments_json: JSON string of transcript segments
        max_retries: Number of retries for invalid responses
        
    Returns:
        List of 5 validated ClipIdea objects
        
    Raises:
        OpenAIError: If API call fails or validation fails after retries
    """
    client = _get_client()
    model = _get_model()
    
    # Build user prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(segments_json=segments_json)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    
    retries = 0
    last_error: Optional[str] = None
    
    while retries <= max_retries:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            if not content:
                raise OpenAIError("Empty response from OpenAI")
            
            # Parse JSON
            parsed = _parse_response(content)
            
            # Extract ideas
            raw_ideas = parsed.get("ideas", [])
            if not isinstance(raw_ideas, list):
                raise OpenAIError("Response 'ideas' is not a list")
            
            # Validate ideas
            valid_ideas, needs_regeneration = validate_ideas(raw_ideas)
            
            if not needs_regeneration and len(valid_ideas) == 5:
                return valid_ideas
            
            # Need to retry
            if retries < max_retries:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": RETRY_PROMPT})
                last_error = f"Got {len(valid_ideas)} valid ideas, need 5"
            else:
                # Return what we have if at least 3 valid
                if len(valid_ideas) >= 3:
                    # Pad with duplicates if needed (not ideal but acceptable for MVP)
                    while len(valid_ideas) < 5:
                        valid_ideas.append(valid_ideas[-1])
                    return valid_ideas[:5]
                raise OpenAIError(f"Could not get 5 valid ideas: {last_error}")
            
        except OpenAIError:
            raise
        except Exception as e:
            if retries >= max_retries:
                raise OpenAIError(f"OpenAI API error: {e}")
            messages.append({"role": "user", "content": RETRY_PROMPT})
            last_error = str(e)
        
        retries += 1
    
    raise OpenAIError("Failed to generate valid clip ideas after retries")
