import pytest
import os
import json
import uuid
from backend.learning_loop import LearningLoopController
from backend.models import ResolutionCaptureRequest
from backend.mcp_client import McpAtlassianCloudError
from pydantic import ValidationError

def test_pydantic_rejects_blank_resolution_submissions():
    """
    Verifies `EC-5.3`: Pydantic v2 schema validation rejects blank or vague resolution
    submissions (`min_length=15` for precursor, `min_length=30` for narrative) before external write.
    """
    with pytest.raises(ValidationError) as exc_info:
        ResolutionCaptureRequest(
            alert_signature="MemoryPoolExhaustedException",
            precursor_condition="short",
            resolution_narrative="fixed it"
        )
    err_msg = str(exc_info.value)
    assert "precursor_condition" in err_msg or "String should have at least 15 characters" in err_msg
    assert "resolution_narrative" in err_msg or "String should have at least 30 characters" in err_msg

def test_learning_loop_sha256_deduplication():
    """
    Verifies `EC-5.1`: Submitting identical resolution requests across a 30-minute window
    skips duplicate ticket creation, merges status, and returns `DUPLICATE_DEDUPLICATED`.
    """
    uid = uuid.uuid4().hex[:8]
    req = ResolutionCaptureRequest(
        alert_signature=f"UniqueShaTestSignature_{uid}",
        precursor_condition=f"Unique root cause triggered by concurrent thread leak {uid}",
        resolution_narrative="Increase thread pool max size to 500 in application.yml and restart."
    )
    
    # First submission -> SUCCESS
    res1 = LearningLoopController.capture_and_externalize(req)
    assert res1["status"] in ["SUCCESS", "LOCAL_FALLBACK_SAVED"]
    
    # Second immediate submission -> DUPLICATE_DEDUPLICATED (`EC-5.1`)
    res2 = LearningLoopController.capture_and_externalize(req)
    assert res2["status"] == "DUPLICATE_DEDUPLICATED"
    assert "EC-5.1" in res2["message"]
    assert res2["kb_id"] == res1["kb_id"]

def test_learning_loop_dual_storage_read_only_fallback():
    """
    Verifies `EC-5.2`: When Atlassian MCP throws HTTP 403 / 503 Permission/Server Error,
    the write-back controller logs task to `pending_jira_sync.log` and saves directly
    to `data/kb_store.json` with `sync_status = PENDING_JIRA_SYNC`.
    """
    uid = uuid.uuid4().hex[:8]
    req = ResolutionCaptureRequest(
        alert_signature=f"CloudMaintenanceTestAlert_{uid}",
        precursor_condition=f"Database connection pool exhaustion on reporting node {uid}",
        resolution_narrative="Flush Hikari pool via JMX console and re-enable read replicas."
    )
    
    # Monkey-patch mcp_client to throw 503 Atlassian Cloud Error
    from backend import learning_loop
    orig_create = learning_loop.mcp_client.execute_create_issue
    def mock_503_create(*args, **kwargs):
        raise McpAtlassianCloudError("HTTP 503 Service Unavailable (Atlassian Cloud maintenance)")
    
    learning_loop.mcp_client.execute_create_issue = mock_503_create
    try:
        res = LearningLoopController.capture_and_externalize(req)
        assert res["status"] == "LOCAL_FALLBACK_SAVED"
        assert res["sync_status"] == "PENDING_JIRA_SYNC"
        
        # Verify saved directly in local store
        store_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kb_store.json")
        with open(store_path, "r", encoding="utf-8") as f:
            records = json.load(f)
            saved_rec = next((r for r in records if r["alert_signature"] == f"CloudMaintenanceTestAlert_{uid}"), None)
            assert saved_rec is not None
            assert saved_rec["sync_status"] == "PENDING_JIRA_SYNC"
    finally:
        learning_loop.mcp_client.execute_create_issue = orig_create
