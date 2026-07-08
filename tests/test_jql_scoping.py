import pytest
from backend.jql_translator import ScopedJqlTranslator, truncate_alert_trace, escape_jql_terms
from backend.config import settings

def test_alert_trace_truncation_under_1500_chars():
    """
    Verifies `EC-1.1`: 25,000-character stack dumps are trimmed to <= 1,500 + safety notice characters,
    preserving top exception headers and bottom root cause lines.
    """
    header = "java.lang.OutOfMemoryError: Java heap space on app-node-01\n"
    body = "at com.bank.stmt.BatchProcessor.run(BatchProcessor.java:142)\n" * 500
    footer = "Caused by: MemoryPoolExhaustedException in ReconcileTask\n"
    massive_trace = header + body + footer
    
    assert len(massive_trace) > 25000
    truncated = truncate_alert_trace(massive_trace, max_chars=1500)
    
    assert len(truncated) < 1700 # 1500 + truncation notice string length
    assert "java.lang.OutOfMemoryError" in truncated
    assert "MemoryPoolExhaustedException" in truncated
    assert "EC-1.1 Truncated" in truncated

def test_escape_jql_terms_and_sanitization():
    """
    Verifies `EC-1.4`: Unescaped JQL reserved chars ([ ] ( ) + - ! * ? ~ ^ { } " \\ :)
    and SQL comment strings are sanitized to prevent HTTP 400 crashes.
    """
    dangerous_input = 'MemoryPoolExhausted [ERROR] -- OR 1=1 AND text ~ "secret" + * ?'
    escaped = escape_jql_terms(dangerous_input)
    
    assert "--" not in escaped
    assert "OR 1=1" not in escaped
    assert "[" not in escaped and "]" not in escaped
    assert 'text ~ "MemoryPoolExhausted"' in escaped

def test_non_bypassable_jql_scoping():
    """
    Verifies `EC-1.3`: The translator strips explicit PROJECT clauses from input/LLM
    and forcefully wraps the result inside PROJECT in ("CR") AND (...) ORDER BY created DESC.
    """
    injection_attempt = "MemoryPoolExhausted AND PROJECT in (HR_PAYROLL, TRADING) ORDER BY priority ASC"
    jql = ScopedJqlTranslator.translate_to_jql(injection_attempt)
    
    allowed_keys = settings.jira_project_keys
    assert f'PROJECT in ("{allowed_keys[0]}") AND (' in jql
    assert "HR_PAYROLL" not in jql.split("AND")[0] # Cannot override project clause at start
    assert "ORDER BY created DESC" in jql
