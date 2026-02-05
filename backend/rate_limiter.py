"""
In-memory rate limiter for MVP.
Tracks requests per IP per day.
"""

import os
from datetime import date
from typing import Dict, Tuple


class RateLimiter:
    """Simple in-memory rate limiter tracking daily requests per IP."""
    
    def __init__(self):
        # Structure: {ip: {date_str: count}}
        self._requests: Dict[str, Dict[str, int]] = {}
        self._daily_limit = int(os.getenv("DAILY_LIMIT_PER_IP", "20"))
    
    def _get_today(self) -> str:
        """Get today's date as a string."""
        return date.today().isoformat()
    
    def _cleanup_old_entries(self, ip: str) -> None:
        """Remove entries from previous days for this IP."""
        today = self._get_today()
        if ip in self._requests:
            self._requests[ip] = {
                d: count for d, count in self._requests[ip].items()
                if d == today
            }
    
    def check_and_increment(self, ip: str) -> Tuple[bool, int]:
        """
        Check if IP is within rate limit and increment counter.
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        today = self._get_today()
        
        # Initialize IP entry if not exists
        if ip not in self._requests:
            self._requests[ip] = {}
        
        # Cleanup old entries
        self._cleanup_old_entries(ip)
        
        # Get current count for today
        current_count = self._requests[ip].get(today, 0)
        
        if current_count >= self._daily_limit:
            return False, 0
        
        # Increment counter
        self._requests[ip][today] = current_count + 1
        remaining = self._daily_limit - (current_count + 1)
        
        return True, remaining
    
    def get_remaining(self, ip: str) -> int:
        """Get remaining requests for an IP today."""
        today = self._get_today()
        current_count = self._requests.get(ip, {}).get(today, 0)
        return max(0, self._daily_limit - current_count)


# Global instance
rate_limiter = RateLimiter()
