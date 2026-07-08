import hashlib
import time
import re
from typing import Any, Optional, Dict

class LRUCache:
    """
    In-memory LRU Cache with 15-minute TTL (`EC-3.1`).
    Intercepts identical or near-identical alert traces submitted during active outages,
    serving cached results in < 50ms with zero Groq API tokens consumed.
    """
    def __init__(self, max_size: int = 500, ttl_seconds: int = 900):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def normalize_key(alert_trace: str) -> str:
        """
        Normalizes input trace by stripping timestamps, memory addresses, and extra whitespace,
        then returns SHA-256/MD5 hash for exact matching.
        """
        # Remove common transient hex memory addresses e.g., 0x7fff5fbff6c0 or @2f3a4b
        cleaned = re.sub(r'0x[0-9a-fA-F]+|@[0-9a-fA-F]+', '', alert_trace)
        # Collapse whitespace and lowercase
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
        return hashlib.md5(cleaned.encode('utf-8')).hexdigest()

    def get(self, alert_trace: str) -> Optional[Any]:
        """Returns cached payload if present and within TTL, otherwise None."""
        key = self.normalize_key(alert_trace)
        if key not in self.cache:
            self.misses += 1
            return None
        
        entry = self.cache[key]
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            # Expired
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        # Move to end to maintain LRU order
        self.cache[key] = self.cache.pop(key)
        return entry["value"]

    def set(self, alert_trace: str, value: Any) -> None:
        """Stores value in cache with current timestamp, evicting oldest entry if full."""
        key = self.normalize_key(alert_trace)
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.max_size:
            # Evict oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = {
            "value": value,
            "timestamp": time.time()
        }

    def clear(self) -> None:
        """Clears all entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> Dict[str, Any]:
        """Returns cache stats."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self.hits,
            "misses": self.misses
        }

# Global cache instance
lru_cache = LRUCache()
