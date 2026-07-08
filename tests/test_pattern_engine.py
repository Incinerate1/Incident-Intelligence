import pytest
from backend.pattern_engine import PatternEngine
from backend.models import SemanticMatchResult, JiraTicketCandidate, PatternResponse

def test_pattern_engine_sparse_thresholds():
    """
    Verifies `EC-4.1` & `EC-4.3`:
    - count == 0 -> NO_MATCHES_FOUND (`EC-4.3`)
    - count in [1, 2] -> LOW_CONFIDENCE_SPARSE (`EC-4.1`) with clickable URLs populated
      and generalized precursor/owner claims explicitly suppressed.
    """
    # Zero match
    res_zero = PatternEngine.synthesize_pattern([])
    assert res_zero.status == "NO_MATCHES_FOUND"
    assert "EC-4.3" in (res_zero.warning_message or "")
    
    # 2 matches (sparse)
    m1 = SemanticMatchResult(candidate=JiraTicketCandidate(issue_key="CR-1", summary="Er1", description="desc1"), is_semantic_match=True, confidence_score=0.8)
    m2 = SemanticMatchResult(candidate=JiraTicketCandidate(issue_key="CR-2", summary="Er2", description="desc2"), is_semantic_match=True, confidence_score=0.7)
    
    res_sparse = PatternEngine.synthesize_pattern([m1, m2])
    assert res_sparse.status == "LOW_CONFIDENCE_SPARSE"
    assert res_sparse.precursor_condition == "Unverified (Sparse historical data)"
    assert res_sparse.escalation_owner == "Unverified (Requires manual triage)"
    assert res_sparse.pattern_count == 2
    assert "browse/CR-1" in res_sparse.matched_tickets
    assert "EC-4.1" in (res_sparse.warning_message or "")

def test_pattern_engine_verified_kb_override():
    """
    Verifies `EC-4.2`: When count == 1, but candidate has verified KB tag,
    the engine immediately returns VERIFIED_KB_RESOLUTION, overriding the sparse threshold.
    """
    cand = JiraTicketCandidate(
        issue_key="CR-104",
        summary="Resolved: JVM Heap Overflow",
        description="[INCIDENT_INTELLIGENCE_KB_ENTRY] Set JVM heap to -Xmx16g on reporting service.",
        has_verified_kb_entry=True
    )
    m = SemanticMatchResult(candidate=cand, is_semantic_match=True, confidence_score=1.0)
    
    res = PatternEngine.synthesize_pattern([m])
    assert res.status == "VERIFIED_KB_RESOLUTION"
    assert res.precursor_condition == "JVM Heap Overflow"
    assert "Set JVM heap to -Xmx16g" in res.resolution_steps
    assert res.warning_message is None

def test_pattern_engine_majority_rule_varied_triggers():
    """
    Verifies `EC-3.2`: When count >= 3 and triggers vary widely without >50% consensus,
    the engine outputs exact varied triggers notice and warning banner.
    """
    c1 = JiraTicketCandidate(issue_key="CR-10", summary="Timeout on gateway", description="Network switch lag")
    c2 = JiraTicketCandidate(issue_key="CR-11", summary="Disk full on db node", description="Logs filled disk")
    c3 = JiraTicketCandidate(issue_key="CR-12", summary="Bad deployment script", description="Missing jar dependency")
    
    matches = [
        SemanticMatchResult(candidate=c1, is_semantic_match=True, confidence_score=0.9),
        SemanticMatchResult(candidate=c2, is_semantic_match=True, confidence_score=0.85),
        SemanticMatchResult(candidate=c3, is_semantic_match=True, confidence_score=0.8)
    ]
    
    # Monkey-patch LLM client to return varied consensus
    from backend import pattern_engine
    orig_generate = pattern_engine.llm_client.generate
    def mock_varied_generate(*args, **kwargs):
        return '{"precursor_condition": "No single dominant precursor condition across matches (varied triggers).", "escalation_owner": "Multiple Teams", "has_majority_consensus": false}'
    
    pattern_engine.llm_client.generate = mock_varied_generate
    try:
        res = PatternEngine.synthesize_pattern(matches)
        assert res.status == "HIGH_CONFIDENCE_PATTERN"
        assert res.precursor_condition == "No single dominant precursor condition across matches (varied triggers)."
        assert "EC-3.2" in (res.warning_message or "")
    finally:
        pattern_engine.llm_client.generate = orig_generate
