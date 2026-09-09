"""
Application Settings
====================
Pydantic BaseSettings reads from environment variables and .env file.
Centralizes all configuration parameters for scraping, filtering, and server options.
"""

from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dynamically locate the .env file with root fallback
_env_path = find_dotenv(usecwd=True)
if not _env_path:
    _candidate = Path(__file__).resolve().parent.parent.parent / ".env"
    if _candidate.exists():
        _env_path = str(_candidate)


class Settings(BaseSettings):
    """Central application configuration."""

    model_config = SettingsConfigDict(
        env_file=_env_path or ".env",
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
    scraper_parser_engine: str = Field(default="selectolax", description="Default parser engine")
    proxy_list: list[str] = Field(default_factory=list, description="List of proxy URLs (optional, e.g. http://user:pass@host:port)")
    proxy_rotation: bool = Field(default=False, description="Enable proxy rotation per country")

    # Filtering
    filter_max_age_hours: int = Field(default=720, description="Max job age in hours (30 days)")

    # Server Configuration
    dashboard_host: str = Field(default="127.0.0.1", description="Server host IP")
    dashboard_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("PORT", "port", "dashboard_port"),
        description="Server port",
    )

    # SharePoint & Azure AD Graph API Settings (strictly loaded from .env)
    azure_tenant_id: str = Field(default="", description="Azure AD Tenant ID")
    azure_client_id: str = Field(default="", description="Azure AD Application (Client) ID")
    azure_client_secret: str = Field(default="", description="Azure AD Client Secret")
    sharepoint_site_id: str = Field(default="", description="SharePoint Site ID")
    sharepoint_hostname: str = Field(default="", description="SharePoint Tenant Hostname (e.g. yourtenant.sharepoint.com)")
    sharepoint_site_path: str = Field(default="", description="SharePoint Site Path (e.g. /sites/yourteam)")
    sharepoint_list_id: str = Field(default="", description="SharePoint List ID")
    sharepoint_list_name: str = Field(default="", description="SharePoint List Name")
    sharepoint_auto_sync: bool = Field(default=False, description="Auto-upload scraped jobs to SharePoint List")

    # Azure AI Search (existing company knowledge-base index)
    azure_search_endpoint: str = Field(default="", description="Azure AI Search service endpoint URL")
    azure_search_index: str = Field(default="", description="Azure AI Search index name (existing KB index)")
    azure_search_api_key: str = Field(default="", description="Azure AI Search admin/query API key")
    azure_search_top_k: int = Field(default=5, description="Number of KB chunks to retrieve per job")

    # LLM Provider Selection Toggle
    # If USE_AZURE_MODEL=true -> uses Azure AI Foundry / Azure OpenAI (Phi-4-mini-instruct / gpt-4o-mini)
    # If USE_AZURE_MODEL=false -> uses OpenRouter free Gemma 4 model (google/gemma-4-31b-it:free)
    use_azure_model: bool = Field(default=False, description="True to use Azure model; False to use free OpenRouter Gemma-4 model")

    # LLM Settings (supports Azure OpenAI / Azure AI Foundry / OpenRouter / NVIDIA NIM)
    llm_provider: str = Field(default="azure", description="LLM provider: 'azure', 'openrouter', 'openai', or 'nvidia'")
    
    # OpenRouter Settings (Free models e.g. google/gemma-4-31b-it:free)
    openrouter_api_key: str = Field(default="", description="OpenRouter API Key")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter Base URL")
    openrouter_model: str = Field(default="google/gemma-4-31b-it:free", description="OpenRouter Model Identifier")

    nvidia_api_key: str = Field(default="", description="NVIDIA NIM API key")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA NIM base URL")
    nvidia_model: str = Field(default="nvidia/nemotron-3-ultra-550b-a55b", description="NVIDIA model name")

    # Azure OpenAI (Legacy / Alternative)
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_openai_api_version: str = Field(default="2024-06-01", description="Azure OpenAI REST API version")
    azure_openai_chat_deployment: str = Field(default="", description="Azure OpenAI chat deployment name used for match evaluation")

    # Knowledge-base matching toggle
    enable_kb_matching: bool = Field(default=True, description="Enrich scraped jobs with Azure KB retrieval + LLM match scoring")

    # Directories
    output_dir: str = Field(default="outputs", description="Excel output directory")
    log_dir: str = Field(default="logs", description="Log file directory")


_settings = None


def get_settings() -> Settings:
    """Return singleton Settings instance with credentials loaded strictly from .env."""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Ensure output and log directories exist
        Path(_settings.output_dir).mkdir(parents=True, exist_ok=True)
        Path(_settings.log_dir).mkdir(parents=True, exist_ok=True)
    return _settings
