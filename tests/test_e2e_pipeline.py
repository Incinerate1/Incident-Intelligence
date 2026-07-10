import time
import pytest
import uuid
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_e2e_latency_and_scan_ability():
    """
    Verifies `Verification Criteria Phase 4`:
    - Full triage pipeline (`JQL -> MCP search -> Grounding -> Synthesis -> JSON render`)
      completes in < 15.0 seconds (Target: ~0.5s local / < 15.0s online).
    - Structured badges (`status`, `precursor_condition`, `escalation_owner`, `summary_stats`, `matched_tickets`)
      are populated for instant < 10s scannability.
    """
    query = "MemoryPoolExhaustedException during stmt_gen_eod batch run on reporting node 04"
    start_time = time.time()
    
    response = client.post("/api/v1/triage", json={"alert_trace": query})
    elapsed = time.time() - start_time
    
    assert response.status_code == 200
    assert elapsed < 15.0
    
    data = response.json()
    pattern = data["pattern"]
    meta = data["meta"]
    
    # Scannability assertions
    assert pattern["status"] in ["VERIFIED_KB_RESOLUTION", "HIGH_CONFIDENCE_PATTERN", "LOW_CONFIDENCE_SPARSE", "NO_MATCHES_FOUND"]
    assert "precursor_condition" in pattern
    assert "escalation_owner" in pattern
    assert "summary_stats" in pattern
    assert isinstance(pattern["matched_tickets"], list)
    assert meta["elapsed_seconds"] < 15.0

def test_e2e_continuous_learning_and_deduplication_loop():
    """
    Verifies `Verification Criteria Phase 4 Continuous Learning Suite`:
    1. Submit novel error -> NO_MATCHES_FOUND (`EC-4.3`)
    2. Submit malformed resolution -> HTTP 422 (`EC-5.3`)
    3. Submit valid resolution -> SUCCESS (`EC-5.2`)
    4. Re-submit resolution -> DUPLICATE_DEDUPLICATED (`EC-5.1`)
    5. Re-triage original error -> VERIFIED_KB_RESOLUTION (`EC-4.2`)
    """
    uid = uuid.uuid4().hex[:8]
    novel_error = f"UniqueNeverSeenAlertTrace_{uid} in sector_{uid}"
    
    # 1. Novel error check (`EC-4.3`)
    res_triage1 = client.post("/api/v1/triage", json={"alert_trace": novel_error})
    assert res_triage1.status_code == 200
    assert res_triage1.json()["pattern"]["status"] == "NO_MATCHES_FOUND"
    
    # 2. Malformed resolution (`EC-5.3`)
    res_invalid = client.post("/api/v1/capture-resolution", json={
        "alert_signature": novel_error,
        "precursor_condition": "too short",
        "resolution_narrative": "fixed it"
    })
    assert res_invalid.status_code == 422
    assert "EC-5.3" in res_invalid.text
    
    # 3. Valid resolution capture (`EC-5.2`)
    res_valid = client.post("/api/v1/capture-resolution", json={
        "alert_signature": novel_error,
        "precursor_condition": f"Thread deadlock caused by unreleased mutex lock {uid}",
        "resolution_narrative": "Increase lock acquire timeout to 5000ms in ThreadPoolConfig.java and restart service worker."
    })
    assert res_valid.status_code == 200
    data_valid = res_valid.json()
    assert data_valid["status"] in ["SUCCESS", "LOCAL_FALLBACK_SAVED"]
    
    # 4. Immediate duplicate resolution check (`EC-5.1`)
    res_dup = client.post("/api/v1/capture-resolution", json={
        "alert_signature": novel_error,
        "precursor_condition": f"Thread deadlock caused by unreleased mutex lock {uid}",
        "resolution_narrative": "Increase lock acquire timeout to 5000ms in ThreadPoolConfig.java and restart service worker."
    })
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "DUPLICATE_DEDUPLICATED"
    
    # 5. Re-triage original error (`EC-4.2` instant priority override)
    res_triage2 = client.post("/api/v1/triage", json={"alert_trace": novel_error})
    assert res_triage2.status_code == 200
    pattern2 = res_triage2.json()["pattern"]
    assert pattern2["status"] == "VERIFIED_KB_RESOLUTION"
    assert "Increase lock acquire timeout" in pattern2["resolution_steps"]

def test_e2e_weekly_summary_endpoint():
    """Verifies shift manager weekly summary mode API endpoint (`Step 4.3`)."""
    response = client.get("/api/v1/weekly-summary?project=CR&days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["project_key"] == "CR"
    assert isinstance(data["clusters"], list)
    assert data["status"] == "SUCCESS"
