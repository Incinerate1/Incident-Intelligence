import os
import json
from typing import List, Dict, Any, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Core runtime configuration settings loaded from environment variables or .env file.
    Enforces mandatory project scoping (`EC-1.3`) and validates API credentials.
    """
    groq_api_key: str = Field("", alias="GROQ_API_KEY", description="Groq Cloud API Key (gsk_...)")
    atlassian_cloud_url: str = Field("https://amanshende652.atlassian.net/", alias="ATLASSIAN_CLOUD_URL")
    atlassian_client_id: str = Field("", alias="ATLASSIAN_CLIENT_ID")
    atlassian_client_secret: str = Field("", alias="ATLASSIAN_CLIENT_SECRET")
    atlassian_mcp_config_raw: Union[str, Dict[str, Any]] = Field("{}", alias="ATLASSIAN_MCP_CONFIG")
    jira_project_keys_raw: str = Field("CR", alias="JIRA_PROJECT_KEYS")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def jira_project_keys(self) -> List[str]:
        """Returns clean list of allowed project keys e.g. ['CR', 'OPS']."""
        if not self.jira_project_keys_raw:
            return ["CR"]
        keys = [k.strip().replace('"', '').replace("'", "") for k in self.jira_project_keys_raw.split(",") if k.strip()]
        if not keys:
            raise ValueError("EC-1.3 Scoping Error: JIRA_PROJECT_KEYS cannot be empty.")
        return keys

    @property
    def atlassian_mcp_config(self) -> Dict[str, Any]:
        """Returns parsed dict for Atlassian MCP configuration."""
        if isinstance(self.atlassian_mcp_config_raw, dict):
            return self.atlassian_mcp_config_raw
        try:
            return json.loads(self.atlassian_mcp_config_raw)
        except Exception:
            return {
                "auth_type": "oauth",
                "client_id": self.atlassian_client_id,
                "client_secret": self.atlassian_client_secret
            }

settings = Settings()
