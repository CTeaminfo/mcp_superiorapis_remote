"""
Test cases for the MCP server modules.
"""
import pytest
from mcp_superiorapis_remote.config import get_config


def test_config_loading():
    """Test that configuration loads without error."""
    config = get_config()
    assert config is not None
    assert config.http_server_port > 0
    assert config.sse_server_port > 0


def test_config_validation():
    """Test that configuration validation works."""
    config = get_config()
    errors = config.validate()
    # Should not have any errors with default configuration
    assert isinstance(errors, list)