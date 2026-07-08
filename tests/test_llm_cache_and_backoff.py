import time
import pytest
from backend.cache import LRUCache, lru_cache
from backend.llm_client import GroqClientWrapper, GroqTimeoutError

def test_lru_cache_sub_50ms_retrieval_and_normalization():
    """
    Verifies `EC-3.1`: LRU Cache normalizes memory addresses and returns cached
    outage repeat queries in < 50ms without consuming Groq API tokens.
    """
    cache = LRUCache(max_size=100, ttl_seconds=900)
    trace_run_1 = "MemoryPoolExhaustedException on node app-rep-04 at 0x7fff5fbff6c0 during stmt_gen_eod"
    trace_run_2 = "  memorypoolexhaustedexception ON NODE app-rep-04 AT 0x123456789abc DURING stmt_gen_eod  "
    
    # Check normalization produces identical keys
    assert cache.normalize_key(trace_run_1) == cache.normalize_key(trace_run_2)
    
    mock_pattern_response = {"status": "HIGH_CONFIDENCE_PATTERN", "precursor": "JVM Heap Overflow"}
    cache.set(trace_run_1, mock_pattern_response)
    
    start = time.time()
    cached_val = cache.get(trace_run_2)
    elapsed = time.time() - start
    
    assert cached_val == mock_pattern_response
    assert elapsed < 0.05, f"Expected cache hit in < 50ms (`EC-3.1`), but took {elapsed:.4f}s"
    assert cache.hits == 1

def test_lru_cache_eviction_and_ttl():
    """Verifies cache TTL and LRU eviction mechanics."""
    cache = LRUCache(max_size=2, ttl_seconds=1)
    cache.set("alert1", "val1")
    cache.set("alert2", "val2")
    cache.set("alert3", "val3") # Evicts alert1
    
    assert cache.get("alert1") is None
    assert cache.get("alert2") == "val2"
    assert cache.get("alert3") == "val3"
    
    # Simulate TTL expiration
    cache.cache[cache.normalize_key("alert2")]["timestamp"] = time.time() - 10
    assert cache.get("alert2") is None

def test_groq_preflight_budget_and_timeout_circuit_breaker():
    """
    Verifies `EC-3.1` preflight tracking and `EC-3.3` stage timeout circuit breaker.
    """
    wrapper = GroqClientWrapper(api_key="mock_key")
    assert wrapper.check_rate_limit_preflight(estimated_tokens=500) is True
    
    # Simulate exhausting rolling token budget
    wrapper.token_count_window = 11800
    assert wrapper.check_rate_limit_preflight(estimated_tokens=500) is False
    
    # Verify stage generation timeout circuit breaker raises GroqTimeoutError (`EC-3.3`)
    with pytest.raises(GroqTimeoutError) as exc_info:
        # Simulate a 4.5s stage timeout triggered when execution takes longer than timeout_seconds=0.1
        wrapper.generate("test prompt", timeout_seconds=0.001)
    
    assert "EC-3.3" in str(exc_info.value)
