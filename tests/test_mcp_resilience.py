import time
import pytest
from backend.mcp_client import McpClientWrapper, McpConnectionError, McpAuthError, McpAtlassianCloudError
from backend.config import settings

def test_mcp_mandatory_jql_scoping():
    """
    Verifies `EC-1.3`: Invoking `jira_search_issues` without allowed project keys (`CR`)
    throws ValueError before any external network invocation occurs.
    """
    mcp = McpClientWrapper()
    
    # Valid scoped JQL
    res = mcp.execute_jira_search('PROJECT in ("CR") AND text ~ "exception" ORDER BY created DESC')
    assert isinstance(res, list)
    
    # Invalid unscoped global JQL -> must raise ValueError
    with pytest.raises(ValueError) as exc_info:
        mcp.execute_jira_search('text ~ "MemoryPoolExhausted" ORDER BY created DESC')
    assert "EC-1.3 Scoping Error" in str(exc_info.value)

def test_mcp_timeout_circuit_breaker():
    """
    Verifies `EC-2.1`: When Atlassian MCP tool execution exceeds 3.0 seconds,
    the circuit breaker opens and raises McpConnectionError for immediate local KB fallback.
    """
    mcp = McpClientWrapper(timeout_seconds=0.01) # Set strict timeout for testing
    
    # Monkey-patch dispatch to simulate slow Atlassian network
    def slow_dispatch(*args, **kwargs):
        time.sleep(0.05)
        return []
    mcp._dispatch_tool_mock_or_real = slow_dispatch
    
    with pytest.raises(McpConnectionError) as exc_info:
        mcp.execute_jira_search('PROJECT in ("CR") ORDER BY created DESC')
    
    assert "EC-2.1" in str(exc_info.value)
    assert time.time() < mcp.circuit_breaker_open_until

def test_mcp_sync_auth_refresh_and_retry():
    """
    Verifies `EC-2.2`: Intercepting 401 OAuth expiration triggers synchronous token refresh (<500ms)
    and retries the tool invocation successfully.
    """
    mcp = McpClientWrapper()
    attempt_counter = 0
    
    def auth_retry_dispatch(tool_name, params):
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter == 1:
            raise McpAuthError("Simulated 401 OAuth token expired")
        return {"status": "success", "issue_key": "CR-101"}
    
    mcp._dispatch_tool_mock_or_real = auth_retry_dispatch
    res = mcp.execute_add_comment("CR-101", "Test resolution note")
    
    assert res["status"] == "success"
    assert attempt_counter == 2 # 1 failure + 1 successful retry

def test_mcp_cloud_maintenance_isolation():
    """
    Verifies `EC-2.3`: Intercepting HTTP 503 / 429 opens circuit breaker for 300 seconds.
    """
    mcp = McpClientWrapper()
    
    def maintenance_dispatch(*args, **kwargs):
        raise McpAtlassianCloudError("HTTP 503 Service Unavailable (Cloud Maintenance)")
    
    mcp._dispatch_tool_mock_or_real = maintenance_dispatch
    
    with pytest.raises(McpConnectionError) as exc_info:
        mcp.execute_jira_search('PROJECT in ("CR") ORDER BY created DESC')
    
    assert "EC-2.3 Atlassian Cloud offline" in str(exc_info.value)
    assert mcp.circuit_breaker_open_until > time.time() + 290.0
