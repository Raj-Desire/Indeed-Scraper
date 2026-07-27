"""
Application Settings
====================
Pydantic BaseSettings reads from environment variables and .env file.
Centralizes all configuration parameters for scraping, filtering, and server options.
"""

from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Scraper Configuration
    scraper_headless: bool = Field(default=True, description="Run browser in background")
    scraper_delay_min: float = Field(default=2.0, description="Min request delay (s)")
    scraper_delay_max: float = Field(default=5.0, description="Max request delay (s)")
    scraper_max_pages: int = Field(default=3, description="Default max pages per search")
    scraper_retry_attempts: int = Field(default=3, description="Retry attempts on failure")
    scraper_parser_engine: str = Field(default="beautifulsoup", description="Default parser engine")

    # Filtering
    filter_max_age_hours: int = Field(default=720, description="Max job age in hours (30 days)")

    # Server Configuration
    dashboard_host: str = Field(default="127.0.0.1", description="Server host IP")
    dashboard_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("port", "dashboard_port"),
        description="Server port",
    )

    # SharePoint & Azure AD Graph API Settings
    azure_tenant_id: str = Field(default="", description="Azure AD Tenant ID")
    azure_client_id: str = Field(default="", description="Azure AD Application (Client) ID")
    azure_client_secret: str = Field(default="", description="Azure AD Client Secret")
    sharepoint_site_id: str = Field(default="t12y7.sharepoint.com,7956234f-8307-408f-a0d7-dc15c34c77d1,9b682a2d-dce1-4fcf-82c6-307b316ce49d", description="SharePoint Site ID")
    sharepoint_hostname: str = Field(default="", description="SharePoint Tenant Hostname (e.g. yourtenant.sharepoint.com)")
    sharepoint_site_path: str = Field(default="", description="SharePoint Site Path (e.g. /sites/yourteam)")
    sharepoint_list_id: str = Field(default="2a20da41-1397-45a4-a44e-1e15ad135abf", description="SharePoint List ID")
    sharepoint_list_name: str = Field(default="Indeed_Data", description="SharePoint List Name")
    sharepoint_auto_sync: bool = Field(default=False, description="Auto-upload scraped jobs to SharePoint List")

    # Directories
    output_dir: str = Field(default="outputs", description="Excel output directory")
    log_dir: str = Field(default="logs", description="Log file directory")


_settings = None


def get_settings() -> Settings:
    """Return singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Ensure output and log directories exist
        Path(_settings.output_dir).mkdir(parents=True, exist_ok=True)
        Path(_settings.log_dir).mkdir(parents=True, exist_ok=True)
    return _settings
