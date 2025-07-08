"""
MCP SuperiorAPIs Remote - Dynamic integration with Superior APIs via MCP protocol.

This package provides multiple MCP (Model Context Protocol) server implementations
that dynamically integrate with Superior APIs to expose available tools and plugins
as MCP tools.

Available servers:
- HTTP Server: JSON-RPC 2.0 over HTTP with /mcp endpoint
- SSE Server: Server-Sent Events for real-time client communication  
- Config: Centralized configuration management with .env support

Features:
- Dynamic tool generation from Superior APIs OpenAPI schemas
- Token-based authentication with Superior APIs
- Multiple transport protocols (HTTP, SSE)
- Comprehensive error handling and logging
- Environment-based configuration
"""

__version__ = "0.1.0"
__author__ = "Superior APIs Team"
__email__ = "support@superiorapis.com"

# Import main components for easier access
from .config import Config, get_config, reload_config

# Export public API
__all__ = [
    "Config",
    "get_config", 
    "reload_config",
    "__version__",
    "__author__",
    "__email__",
]