"""Tests that new Azure Search / Azure OpenAI settings load with safe defaults."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import Settings


def test_azure_kb_settings_have_safe_defaults():
    s = Settings(_env_file=None)  # ignore local .env so defaults are exercised
    assert s.azure_search_endpoint == ""
    assert s.azure_search_index == ""
    assert s.azure_search_api_key == ""
    assert s.azure_search_top_k == 5
    assert s.azure_openai_endpoint == ""
    assert s.azure_openai_api_key == ""
    assert s.azure_openai_api_version == "2024-06-01"
    assert s.azure_openai_chat_deployment == ""
    assert s.enable_kb_matching is True


if __name__ == "__main__":
    test_azure_kb_settings_have_safe_defaults()
    print("OK")
