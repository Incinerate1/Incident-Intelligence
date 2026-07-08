import json
import os
import time
import hashlib
import logging
from typing import List
from backend.models import ResolutionCaptureRequest, KnowledgeBaseEntry

logger = logging.getLogger("kb_writer")

class KbWriter:
    """
    Known-Error Knowledge Base Markdown Formatter and Local Store Writer (`Step 3.4`).
    Enforces dual storage serialization (`EC-5.2`) and exact hash indexing (`EC-5.1`).
    """
    @staticmethod
    def compute_hash(alert_signature: str, precursor_condition: str) -> str:
        """Computes SHA-256 deduplication key (`EC-5.1`)."""
        raw = f"{alert_signature.strip().lower()}|{precursor_condition.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def format_kb_markdown_block(cls, req: ResolutionCaptureRequest, kb_id: str) -> str:
        content_hash = cls.compute_hash(req.alert_signature, req.precursor_condition)
        return f"""[INCIDENT_INTELLIGENCE_KB_ENTRY]
### Known-Error Resolution Record: {kb_id}
* **Alert Signature:** `{req.alert_signature}`
* **Precursor Condition:** {req.precursor_condition}
* **Escalation Owner:** {req.escalation_owner}
* **Content Hash (`EC-5.1`):** `{content_hash}`

#### Resolution Narrative / Fix Steps (`EC-5.3` Verified):
{req.resolution_narrative}
[/INCIDENT_INTELLIGENCE_KB_ENTRY]"""

    @classmethod
    def save_to_local_store(cls, entry: KnowledgeBaseEntry) -> None:
        """
        Saves or updates KnowledgeBaseEntry inside `data/kb_store.json` (`EC-5.2`).
        """
        store_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kb_store.json")
        os.makedirs(os.path.dirname(store_path), exist_ok=True)

        records = []
        if os.path.exists(store_path):
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        records = data
            except Exception as e:
                logger.warning(f"Error reading local kb_store.json: {e}")

        # Check if record with same kb_id or content_hash exists
        updated = False
        for i, rec in enumerate(records):
            if rec.get("kb_id") == entry.kb_id or (entry.content_hash and rec.get("content_hash") == entry.content_hash):
                records[i] = entry.model_dump()
                updated = True
                break

        if not updated:
            records.append(entry.model_dump())

        try:
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            logger.info(f"Successfully serialized KB record {entry.kb_id} to data/kb_store.json (`sync_status={entry.sync_status}`)")
        except Exception as e:
            logger.error(f"Failed to save to local kb_store.json: {e}")
