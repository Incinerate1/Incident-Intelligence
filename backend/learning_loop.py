import os
import time
import json
import logging
from typing import Dict, Any
from backend.models import ResolutionCaptureRequest, KnowledgeBaseEntry
from backend.kb_writer import KbWriter
from backend.mcp_client import mcp_client, McpConnectionError, McpAtlassianCloudError, McpAuthError
from backend.config import settings

logger = logging.getLogger("learning_loop")

class LearningLoopController:
    """
    Continuous Learning Loop & Post-Resolution Externalization Controller (`JTBD 2`).
    Enforces concurrent write-back deduplication (`EC-5.1`) and Atlassian read-only
    dual storage fallback (`EC-5.2`).
    """
    @classmethod
    def capture_and_externalize(cls, req: ResolutionCaptureRequest) -> Dict[str, Any]:
        content_hash = KbWriter.compute_hash(req.alert_signature, req.precursor_condition)
        now = time.time()

        # 1. Concurrent Write-Back Deduplication (`EC-5.1`)
        store_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kb_store.json")
        if os.path.exists(store_path):
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    existing_records = json.load(f)
                    if isinstance(existing_records, list):
                        for rec in existing_records:
                            rec_hash = rec.get("content_hash") or KbWriter.compute_hash(rec.get("alert_signature", ""), rec.get("precursor_condition", ""))
                            rec_time = rec.get("created_timestamp", 0)
                            # Check exact hash match OR identical signature within 30-minute window (1800s)
                            if rec_hash == content_hash or (rec.get("alert_signature", "").strip().lower() == req.alert_signature.strip().lower() and now - rec_time < 1800.0):
                                logger.info(f"EC-5.1 Deduplication triggered against existing KB record {rec.get('kb_id')}")
                                return {
                                    "status": "DUPLICATE_DEDUPLICATED",
                                    "kb_id": rec.get("kb_id"),
                                    "sync_status": rec.get("sync_status", "SYNCED"),
                                    "message": f"Exact resolution deduplicated against recent write-back {rec.get('kb_id')} within 30-minute window (`EC-5.1`)."
                                }
            except Exception as e:
                logger.warning(f"Error checking deduplication store: {e}")

        # 2. Dual Storage & Read-Only Fallback (`EC-5.2`)
        kb_id = req.existing_issue_key or f"{settings.jira_project_keys[0]}-KB-{int(now % 10000)}"
        kb_block = KbWriter.format_kb_markdown_block(req, kb_id)
        sync_status = "SYNCED"

        try:
            if req.existing_issue_key:
                res = mcp_client.execute_add_comment(req.existing_issue_key, kb_block)
                kb_id = req.existing_issue_key
            else:
                res = mcp_client.execute_create_issue(
                    project=settings.jira_project_keys[0],
                    summary=f"[Known Error] {req.precursor_condition[:60]}",
                    description=kb_block
                )
                if isinstance(res, dict) and "issue_key" in res:
                    kb_id = res["issue_key"]
        except (McpConnectionError, McpAtlassianCloudError, McpAuthError, Exception) as e:
            logger.warning(f"EC-5.2 Atlassian MCP write failure ({e}). Engaging dual storage local fallback (`sync_status = PENDING_JIRA_SYNC`)...")
            sync_status = "PENDING_JIRA_SYNC"
            # Log to pending_jira_sync.log
            log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pending_jira_sync.log")
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    log_entry = {
                        "timestamp": now,
                        "content_hash": content_hash,
                        "kb_id": kb_id,
                        "request": req.model_dump()
                    }
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as log_err:
                logger.error(f"Failed to append to pending_jira_sync.log: {log_err}")

        # 3. Save to local kb_store.json (`EC-5.2` dual storage & `EC-4.2` instant retrieval boost)
        entry = KnowledgeBaseEntry(
            kb_id=kb_id,
            alert_signature=req.alert_signature,
            precursor_condition=req.precursor_condition,
            resolution_narrative=req.resolution_narrative,
            escalation_owner=req.escalation_owner,
            created_timestamp=now,
            sync_status=sync_status,
            content_hash=content_hash
        )
        KbWriter.save_to_local_store(entry)

        return {
            "status": "SUCCESS" if sync_status == "SYNCED" else "LOCAL_FALLBACK_SAVED",
            "kb_id": kb_id,
            "sync_status": sync_status,
            "message": f"Successfully documented Known-Error resolution (`sync_status = {sync_status}`). Instant retrieval boost enabled (`EC-4.2`)."
        }
