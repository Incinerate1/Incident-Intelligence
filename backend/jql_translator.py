import re
import logging
from typing import List
from backend.config import settings
from backend.llm_client import llm_client, GroqRateLimitExceededError, GroqTimeoutError

logger = logging.getLogger("jql_translator")

def truncate_alert_trace(alert_trace: str, max_chars: int = 1500) -> str:
    """
    Mandatory preprocessing truncation (`EC-1.1`).
    Trims massive JVM/Spring memory dumps (`> 25,000 chars`) to 1,500 chars, preserving
    the top exception header and bottom root-cause frames while preventing token overflow.
    """
    trace = alert_trace.strip()
    if len(trace) <= max_chars:
        return trace
    
    half = max_chars // 2
    top_chunk = trace[:half]
    bottom_chunk = trace[-half:]
    return f"{top_chunk}\n... [EC-1.1 Truncated {len(trace) - max_chars} characters for prompt safety] ...\n{bottom_chunk}"

def escape_jql_terms(raw_string: str) -> str:
    """
    Sanitizes and escapes unescaped JQL reserved syntax (`[ ] ( ) + - ! * ? ~ ^ { } " \\ :`)
    to prevent HTTP 400 JQL syntax crashes (`EC-1.4`).
    """
    # Remove dangerous SQL/JQL comment patterns
    cleaned = re.sub(r'--|\bOR\s+1=1\b|\bAND\s+1=1\b', '', raw_string, flags=re.IGNORECASE)
    # Strip any explicit `PROJECT in (...)` clauses so they cannot override scoping (`EC-1.3`)
    cleaned = re.sub(r'PROJECT\s+in\s+\([^)]+\)(\s+AND\s+)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'PROJECT\s*=\s*[^\s\)]+(\s+AND\s+)?', '', cleaned, flags=re.IGNORECASE)
    
    # Extract clean alphanumeric keywords separated by OR
    words = [w.strip() for w in re.split(r'\s+OR\s+|\s+AND\s+|\s+|,|;|\n', cleaned, flags=re.IGNORECASE) if len(w.strip()) > 3]
    valid_words = []
    for w in words:
        # Strip reserved chars
        clean_w = re.sub(r'[\[\]()+!*?~^{}"\\:;]', '', w)
        if len(clean_w) > 3 and clean_w.lower() not in ['error', 'exception', 'failed', 'issue', 'node', 'with', 'from', 'during', 'when', 'that', 'this']:
            valid_words.append(clean_w)
            
    if not valid_words:
        return 'text ~ "error"'
        
    # Take top 4 most distinctive terms
    distinct_terms = list(dict.fromkeys(valid_words))[:4]
    clauses = [f'text ~ "{term}"' for term in distinct_terms]
    return " OR ".join(clauses)

class ScopedJqlTranslator:
    """
    Translates raw triage alerts into strictly scoped Atlassian JQL (`EC-1.3`).
    Enforces truncation (`EC-1.1`), syntax escaping (`EC-1.4`), and non-bypassable scoping.
    """
    @classmethod
    def translate_to_jql(cls, alert_trace: str) -> str:
        truncated_trace = truncate_alert_trace(alert_trace, max_chars=1500)
        
        prompt = f"""
Extract 2 to 4 distinctive technical terms (e.g. exception classes, batch run IDs, or service names) from the following error trace:
---
{truncated_trace}
---
Return ONLY a JQL search clause inside parentheses using text ~ "keyword" separated by OR. Example output: (text ~ "MemoryPoolExhaustedException" OR text ~ "stmt_gen_eod")
Do NOT include PROJECT clauses. Return strictly the search clause.
"""
        try:
            llm_output = llm_client.generate(prompt=prompt, timeout_seconds=4.0)
            sanitized_clause = escape_jql_terms(llm_output)
        except (GroqRateLimitExceededError, GroqTimeoutError, Exception) as e:
            logger.warning(f"EC-3.1 / EC-3.3 JQL LLM translation fallback: {e}. Using deterministic extraction.")
            sanitized_clause = escape_jql_terms(truncated_trace)

        # Enforce non-bypassable scoping (`EC-1.3`)
        allowed_keys = settings.jira_project_keys
        project_scope = '", "'.join(allowed_keys)
        
        # Ensure non-empty terms inside parens
        if not sanitized_clause or sanitized_clause == 'text ~ "error"':
            # Extract directly from trace
            sanitized_clause = escape_jql_terms(truncated_trace)
            
        final_jql = f'PROJECT in ("{project_scope}") AND ({sanitized_clause}) ORDER BY created DESC'
        return final_jql
