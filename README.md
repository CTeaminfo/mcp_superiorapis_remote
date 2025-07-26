# MCP SuperiorAPIs Remote

By deploying this MCP Remote project, you can dynamically integrate Superior API via HTTP/SSE protocols and provide it externally as an MCP tool for AI clients to call.

If you need to integrate using `stdio` mode, please refer to: [CTeaminfo/mcp_superiorapis_local](https://github.com/CTeaminfo/mcp_superiorapis_local)

## 📁 Project Structure

```
mcp_superiorapis_remote/
├── src/mcp_superiorapis_remote/  # Main program
│   ├── __init__.py               # Package initialization
│   ├── config.py                 # Configuration management
│   ├── mcp_server_http.py        # HTTP JSON-RPC 2.0 server
│   └── mcp_server_sse.py         # SSE server
├── tests/                        # Test files
├── .env.example                  # Environment variable example
├── .gitignore                    # Git ignore file
├── mcp_config_example.json       # MCP client config example
├── test_mcp_config.py            # Config test script
├── pyproject.toml                # Project config & dependencies
└── README.md                     # Project documentation (this file)
```

## 🚀 Quick Start

### 1. Environment Preparation

**Prerequisites:**
- Python 3.12+
- Superior APIs Token ([How to get](https://superiorapis-creator.cteam.com.tw))

### 2. Clone the Project

```bash
# Using HTTPS
git clone https://github.com/CTeaminfo/mcp_superiorapis_remote.git

# Using SSH
git clone git@github.com:CTeaminfo/mcp_superiorapis_remote.git
cd mcp_superiorapis_remote
```

### 3. Install uv (if not installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or use pip
pip install uv
```

### 4. Install Dependencies

```bash
# Create virtual environment
uv venv --python 3.12

# Install production dependencies
uv sync

# Or install development dependencies (includes test tools)
uv sync --dev
```

**If you encounter virtual environment errors, try:**
```bash
# Windows (run in cmd or PowerShell)
rmdir /s /q .venv
uv venv --python 3.12
uv sync

# Windows (WSL or Git Bash)
# If unable to delete, restart terminal or use a different name
uv venv .venv_new --python 3.12
rm -rf .venv && mv .venv_new .venv
uv sync

# macOS/Linux
rm -rf .venv
uv venv --python 3.12
uv sync
```

### 5. Configure Environment Variables (Optional)

```bash
# Copy environment variable example file (optional)
cp .env.example .env

# Edit the .env file for custom configuration (optional)
nano .env  # Or use your preferred editor
```

**Token Authentication Instructions:**
```bash
# MCP server acts as a proxy, token is provided by the client request
# Authenticate via HTTP header: token: YOUR_TOKEN
```

**Optional settings (with defaults):**
```bash
HTTP_SERVER_PORT=8000
SSE_SERVER_PORT=8080
LOG_LEVEL=INFO
DEV_MODE=false
```

### 6. Start the Server

```bash
# Using uv scripts (recommended)
uv run start-http    # HTTP server (port 8000)
uv run start-sse     # SSE server (port 8080)

# Or run directly
uv run mcp-superiorapis-http
uv run mcp-superiorapis-sse
```

### 7. Verify Deployment

```bash
# Check server configuration
uv run config

# Check HTTP server health
curl http://localhost:8000/health

# Basic function test (no token required)
uv run test-config

# Full function test (requires Superior APIs token)
uv run test-config --token YOUR_SUPERIOR_APIS_TOKEN
```

### 🔧 Development Commands

Use `uv` built-in scripts:

```bash
# Server startup
uv run start-http      # Start HTTP server
uv run start-sse       # Start SSE server

# Development tools
uv run test            # Run tests
uv run lint            # Lint code
uv run format          # Format code
uv run typecheck       # Type check

# Config check
uv run config          # Check configuration
uv run test-config     # Test server connection
```

### ⚠️ Troubleshooting

1. **Invalid Token Error**
   - Make sure you obtained the correct token from [Superior APIs](https://superiorapis-creator.cteam.com.tw)
   - Token should be provided in the client request, not set on the server

2. **Port Occupied Error**
   - Change `HTTP_SERVER_PORT` or `SSE_SERVER_PORT` in `.env`
   - Or use `lsof -i :8000` to check port usage

3. **Dependency Installation Failure**
   - Ensure Python 3.12+ is installed: `python --version`
   - Ensure uv is installed: `uv --version`
   - Virtual environment issues: On Windows use `rmdir /s /q .venv` in cmd/PowerShell, or refer to the WSL solution above
   - Try clearing cache: `uv cache clean`

4. **Server Startup Failure**
   - Check configuration: `uv run config`
   - View detailed errors: set `LOG_LEVEL=DEBUG` in `.env`

## 🔌 MCP Client Integration

### Multi-Instance Deployment Scenario

Users may need to configure multiple MCP server instances with different tokens to access different Superior APIs toolsets:

```bash
# Start multiple server instances with different ports
HTTP_SERVER_PORT=8000 uv run start-http &
HTTP_SERVER_PORT=8001 uv run start-http &
SSE_SERVER_PORT=8080 uv run start-sse &
```

### Claude Desktop

Configure MCP server using environment variables:

```json
{
  "mcpServers": {
    "mcp-superiorapis-main": {
      "command": "uv",
      "args": ["run", "mcp-superiorapis-http"],
      "env": {
        "TOKEN": "your_main_superior_apis_token_here"
      }
    }
  }
}
```

### Cursor (SSE Mode)

```bash
# Start SSE server
uv run start-sse

# Cursor connects to: http://localhost:8080/sse
```

### HTTP Client

```bash
# Start HTTP server
uv run start-http

# Send JSON-RPC 2.0 request to: http://localhost:8000/mcp
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## 🛠️ Development

### Testing

#### Unit Tests
```bash
# Run unit tests (no need to start server)
uv run test
```

#### Integration Tests
```bash
# Start server first
uv run start-http &

# Basic function test
uv run test-config

# Full function test (requires Superior APIs token)
uv run test-config --token YOUR_TOKEN

# Check configuration
uv run test-config --config
```

### Code Quality

```bash
# Format code
uv run format

# Static checks
uv run lint
uv run typecheck
```

## 📊 Architecture Overview

### Dynamic Tool Generation Flow

1. **Token Authentication** → Superior APIs
2. **Fetch Plugin List** → `plugin list`
3. **Parse OpenAPI Spec** → Auto-generate MCP tool definitions
4. **Cache Tool List** → Improve performance
5. **Handle Tool Calls** → Proxy to Superior APIs

### Supported MCP Methods

- `initialize` - Initialize connection
- `tools/list` - Get available tool list
- `tools/call` - Call specific tool

### Error Handling

- Automatic retry on network errors
- Clear prompt on token authentication failure
- Detailed logs for JSON parsing errors
- Complete JSON-RPC 2.0 error responses

## 🎯 Dify Integration (Latest Update)

### Dify MCP Standalone Server

A specialized server specifically designed for Dify 1.7.0 MCP integration:

```bash
# Start Dify-specific MCP server (port 9000)
python3 dify_mcp_standalone.py
```

**Key Features:**
- **OpenAPI Format Preservation**: Maintains original Superior APIs OpenAPI structure
- **Method-Specific Parsing**: Correctly handles GET (parameters array) vs POST (requestBody)
- **Dify-Optimized**: Designed specifically for Dify MCP SSE plugin compatibility
- **Enhanced Debugging**: Comprehensive logging for troubleshooting

**Configuration:**
```json
{
  "name": "Superior APIs",
  "url": "http://your-server:9000/mcp",
  "headers": {
    "token": "your_superior_apis_token"
  }
}
```

**Testing:**
```bash
# Test Dify MCP endpoint
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

**Recent Fixes:**
- ✅ Fixed 'properties' access error in parameter parsing
- ✅ Corrected OpenAPI path structure (`plugin.interface` vs `plugin_item.openapi`)
- ✅ Implemented proper GET/POST method differentiation
- ✅ Enhanced parameter type allocation (query/path/header/body)

## 🔧 Configuration Options

For full configuration options, see `.env.example`:

| Variable Name | Default | Description |
|--------------|---------|-------------|
| `HTTP_SERVER_PORT` | 8000 | HTTP server port |
| `SSE_SERVER_PORT` | 8080 | SSE server port |
| `LOG_LEVEL` | INFO | Log level |
| `DEV_MODE` | false | Development mode (hot reload) |
| `SERVER_HOST` | 0.0.0.0 | Server host address |
| `CACHE_EXPIRY` | 3600 | Tool cache expiry (seconds) |

**Token Authentication Note**: Superior APIs Token is provided by the client in the HTTP header, not set on the server. Use the `token: YOUR_TOKEN` header for authentication.
