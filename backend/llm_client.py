import time
import random
import logging
from typing import Optional, Dict, Any
from groq import Groq, RateLimitError, APIError, APITimeoutError
from backend.config import settings

logger = logging.getLogger("groq_llm_client")

class GroqRateLimitExceededError(Exception):
    """Raised when Groq free-tier limits (30 RPM / 12k TPM) are persistently breached (EC-3.1)."""
    pass

class GroqTimeoutError(Exception):
    """Raised when stage generation time exceeds 4.5s circuit breaker ceiling (EC-3.3)."""
    pass

class GroqClientWrapper:
    """
    Resilient Groq Cloud wrapper for `llama-3.3-70b-versatile`.
    Enforces rate limit tracking (`30 RPM / 12,000 TPM`), exponential backoff jitter (`EC-3.1`),
    and strict stage timeouts (`4.5s max`, `EC-3.3`) to preserve the < 15.0s SLA.
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or settings.groq_api_key
        self.model = model
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        
        # Rate limit trackers
        self.max_tpm = 12000
        self.max_rpm = 30
        self.token_count_window = 0
        self.request_count_window = 0
        self.window_start_time = time.time()

    def _reset_window_if_needed(self):
        """Resets 60-second rolling window counters."""
        now = time.time()
        if now - self.window_start_time >= 60.0:
            self.token_count_window = 0
            self.request_count_window = 0
            self.window_start_time = now

    def check_rate_limit_preflight(self, estimated_tokens: int = 500) -> bool:
        """
        Preflight check against 12,000 TPM and 30 RPM ceilings (`EC-3.1`).
        Returns True if safe to proceed, False if budget exceeded requiring backoff/fallback.
        """
        self._reset_window_if_needed()
        if self.request_count_window + 1 >= self.max_rpm or (self.token_count_window + estimated_tokens) >= int(self.max_tpm * 0.90):
            return False
        return True

    def generate(self, prompt: str, system_prompt: str = "You are an expert site reliability and pattern recognition assistant.", 
                 response_format: Optional[Dict[str, str]] = None, timeout_seconds: float = 4.5) -> str:
        """
        Executes generation against `llama-3.3-70b-versatile` with exponential backoff (`0.5s->1.0s->2.0s`)
        and strict stage timeout circuit breaker (`EC-3.3`).
        """
        if not self.client:
            raise GroqRateLimitExceededError("Groq API client not initialized (missing API key).")

        estimated_tokens = len(prompt) // 4 + 200
        if not self.check_rate_limit_preflight(estimated_tokens):
            logger.warning("EC-3.1 Rate Limit preflight budget warning: approaching 12k TPM or 30 RPM.")

        backoff_delays = [0.5, 1.0, 2.0]
        start_time = time.time()

        for attempt, delay in enumerate([0.0] + backoff_delays):
            if attempt > 0:
                jitter = delay + random.uniform(0.1, 0.3)
                if time.time() - start_time + jitter > timeout_seconds:
                    raise GroqTimeoutError(f"EC-3.3 Stage generation exceeded {timeout_seconds}s circuit breaker.")
                time.sleep(jitter)

            if time.time() - start_time > timeout_seconds:
                raise GroqTimeoutError(f"EC-3.3 Stage generation exceeded {timeout_seconds}s circuit breaker.")

            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                    "timeout": timeout_seconds - (time.time() - start_time)
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = self.client.chat.completions.create(**kwargs)
                
                # Update counters
                usage = getattr(response, "usage", None)
                used_tokens = getattr(usage, "total_tokens", estimated_tokens) if usage else estimated_tokens
                self.token_count_window += used_tokens
                self.request_count_window += 1

                content = response.choices[0].message.content
                if content is None:
                    return ""
                return content

            except RateLimitError as e:
                logger.warning(f"EC-3.1 Groq RateLimitError on attempt {attempt + 1}: {e}")
                if attempt == len(backoff_delays):
                    raise GroqRateLimitExceededError(f"EC-3.1 Persistent rate limit reached: {e}")
            except (APITimeoutError, Exception) as e:
                err_str = str(e).lower()
                if isinstance(e, APITimeoutError) or "timeout" in err_str or "timed out" in err_str:
                    raise GroqTimeoutError(f"EC-3.3 Groq API timeout: {e}")
                raise e

        raise GroqRateLimitExceededError("EC-3.1 Exhausted exponential backoff retries.")

llm_client = GroqClientWrapper()
