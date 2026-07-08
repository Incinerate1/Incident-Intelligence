import pytest
from backend.semantic_filter import SemanticFilter
from backend.models import JiraTicketCandidate
from backend.llm_client import GroqTimeoutError

def test_semantic_filter_verified_kb_priority_boost():
    """
    Verifies `EC-4.2`: Any candidate with [INCIDENT_INTELLIGENCE_KB_ENTRY] or has_verified_kb_entry=True
    is automatically assigned confidence_score = 1.0 and boosted to the top of results.
    """
    cand_regular = JiraTicketCandidate(issue_key="CR-1", summary="Unrelated node error", description="Some error occurred")
    cand_kb = JiraTicketCandidate(
        issue_key="CR-104",
        summary="Memory pool overflow",
        description="[INCIDENT_INTELLIGENCE_KB_ENTRY] Increase heap memory to 16g.",
        has_verified_kb_entry=True
    )
    
    results = SemanticFilter.filter_and_ground("memory pool exhausted", [cand_regular, cand_kb])
    
    assert len(results) >= 1
    top_res = results[0]
    assert top_res.candidate.issue_key == "CR-104"
    assert top_res.confidence_score == 1.0
    assert top_res.is_semantic_match is True
    assert "EC-4.2" in top_res.reasoning

def test_semantic_filter_ambiguity_noise_rejection():
    """
    Verifies `EC-1.2`: Generic short queries (len < 25) enforce strict matching and reject candidates
    that lack distinct overlap with a score < 0.50 (`NO_MATCHES_FOUND`).
    """
    cand = JiraTicketCandidate(issue_key="CR-20", summary="Database connection deadlocks on login module", description="Re-indexed user DB table.")
    
    # Generic short query (`len < 25`) with no term overlap
    results = SemanticFilter.filter_and_ground("error on node", [cand])
    assert len(results) == 0 # Filtered out because score < 0.55

def test_semantic_filter_deterministic_keyword_fallback():
    """
    Verifies `EC-3.1`/`EC-3.3`: When LLM timeout occurs, the filter gracefully degrades
    to deterministic keyword overlap scoring without breaching SLA.
    """
    cand = JiraTicketCandidate(
        issue_key="CR-55",
        summary="MemoryPoolExhaustedException in stmt_gen_eod batch",
        description="JVM heap exceeded during overnight statement generation run."
    )
    
    # Monkey-patch LLM generate to simulate timeout
    from backend import semantic_filter
    original_generate = semantic_filter.llm_client.generate
    def mock_timeout_generate(*args, **kwargs):
        raise GroqTimeoutError("EC-3.3 Simulated stage timeout")
    semantic_filter.llm_client.generate = mock_timeout_generate
    
    try:
        results = SemanticFilter.filter_and_ground("MemoryPoolExhaustedException during stmt_gen_eod", [cand])
        assert len(results) == 1
        res = results[0]
        assert res.is_semantic_match is True
        assert res.confidence_score >= 0.55
        assert "EC-3.1" in res.reasoning or "EC-3.3" in res.reasoning
    finally:
        semantic_filter.llm_client.generate = original_generate
