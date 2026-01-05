"""
Unit tests for ski forecast Lambda functions.

Validates that imports work correctly and basic functionality is intact.
Run with: python -m pytest ski_forecast/test_lambda.py -v
"""

import sys
import os
from pathlib import Path

# Add lambda directory to path for testing
lambda_dir = Path(__file__).parent / "lambda"
sys.path.insert(0, str(lambda_dir))


def test_ski_analyzer_imports():
    """Test that ski_analyzer can import all required modules."""
    try:
        import ski_analyzer
        assert hasattr(ski_analyzer, 'handler')
        assert hasattr(ski_analyzer, 'invoke_data_fetcher')
        assert hasattr(ski_analyzer, 'call_openai')
        assert hasattr(ski_analyzer, 'post_to_slack')
    except ImportError as e:
        raise AssertionError(f"Failed to import ski_analyzer: {e}")


def test_data_fetcher_imports():
    """Test that data_fetcher can import all required modules."""
    try:
        import data_fetcher
        assert hasattr(data_fetcher, 'handler')
    except ImportError as e:
        raise AssertionError(f"Failed to import data_fetcher: {e}")


def test_config_module_available():
    """Test that config module is available in lambda directory."""
    try:
        import config
        assert hasattr(config, 'get_agent_config')
        assert hasattr(config, 'get_openai_api_url')
        assert hasattr(config, 'load_prompt_text')
    except ImportError as e:
        raise AssertionError(f"Failed to import config: {e}")


def test_config_json_exists():
    """Test that config.json exists in lambda directory."""
    config_path = lambda_dir / "config.json"
    assert config_path.exists(), f"config.json not found at {config_path}"


def test_prompt_file_exists():
    """Test that prompt file exists in lambda directory."""
    prompt_path = lambda_dir / "prompts" / "ski_analyzer_system.txt"
    assert prompt_path.exists(), f"Prompt file not found at {prompt_path}"


def test_ski_analyzer_config_loads():
    """Test that ski_analyzer config loads successfully."""
    import config
    agent_config = config.get_agent_config("ski_analyzer")
    assert "prompt_file" in agent_config
    assert "model" in agent_config
    assert "temperature" in agent_config
    assert "max_completion_tokens" in agent_config


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
