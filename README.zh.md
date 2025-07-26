# MCP SuperiorAPIs Remote

透過部署此 MCP Remote 專案，您可以動態整合 Superior API，並透過 HTTP/SSE 協定向外提供 MCP 工具供 AI 客戶端呼叫。

如果您需要使用 `stdio` 模式進行整合，請參考：[CTeaminfo/mcp_superiorapis_local](https://github.com/CTeaminfo/mcp_superiorapis_local)

## 📁 專案結構

```
mcp_superiorapis_remote/
├── src/mcp_superiorapis_remote/  # 主程式
│   ├── __init__.py               # 套件初始化
│   ├── config.py                 # 配置管理
│   ├── mcp_server_http.py        # HTTP JSON-RPC 2.0 伺服器
│   └── mcp_server_sse.py         # SSE 伺服器
├── tests/                        # 測試檔案
├── .env.example                  # 環境變數範例
├── .gitignore                    # Git 忽略檔案
├── mcp_config_example.json       # MCP 客戶端配置範例
├── test_mcp_config.py            # 配置測試腳本
├── pyproject.toml                # 專案配置與依賴
└── README.md                     # 專案文件（本檔案）
```

## 🚀 快速開始

### 1. 環境準備

**必要條件：**
- Python 3.12+
- Superior APIs Token（[取得方式](https://superiorapis-creator.cteam.com.tw)）

### 2. 複製專案

```bash
# 使用 HTTPS
git clone https://github.com/CTeaminfo/mcp_superiorapis_remote.git

# 使用 SSH
git clone git@github.com:CTeaminfo/mcp_superiorapis_remote.git
cd mcp_superiorapis_remote
```

### 3. 安裝 uv（如果尚未安裝）

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

### 4. 安裝依賴

```bash
# 建立虛擬環境
uv venv --python 3.12

# 安裝生產依賴
uv sync

# 或安裝開發依賴（包含測試工具）
uv sync --dev
```

**如果遇到虛擬環境錯誤，請嘗試：**
```bash
# Windows（在 cmd 或 PowerShell 中執行）
rmdir /s /q .venv
uv venv --python 3.12
uv sync

# Windows（WSL 或 Git Bash）
# 如果無法刪除，請重新啟動終端機或使用不同名稱
uv venv .venv_new --python 3.12
rm -rf .venv && mv .venv_new .venv
uv sync

# macOS/Linux
rm -rf .venv
uv venv --python 3.12
uv sync
```

### 5. 配置環境變數（可選）

```bash
# 複製環境變數範例檔案（可選）
cp .env.example .env

# 編輯 .env 檔案進行自訂配置（可選）
nano .env  # 或使用您偏好的編輯器
```

**Token 驗證說明：**
```bash
# MCP 伺服器作為代理，token 由客戶端請求提供
# 透過 HTTP 標頭驗證：token: YOUR_TOKEN
```

**可選設定（含預設值）：**
```bash
HTTP_SERVER_PORT=8000
SSE_SERVER_PORT=8080
LOG_LEVEL=INFO
DEV_MODE=false
```

### 6. 啟動伺服器

```bash
# 使用 uv 腳本（建議）
uv run start-http    # HTTP 伺服器（埠號 8000）
uv run start-sse     # SSE 伺服器（埠號 8080）

# 或直接執行
uv run mcp-superiorapis-http
uv run mcp-superiorapis-sse
```

### 7. 驗證部署

```bash
# 檢查伺服器配置
uv run config

# 檢查 HTTP 伺服器健康狀態
curl http://localhost:8000/health

# 基本功能測試（不需要 token）
uv run test-config

# 完整功能測試（需要 Superior APIs token）
uv run test-config --token YOUR_SUPERIOR_APIS_TOKEN
```

### 🔧 開發指令

使用 `uv` 內建腳本：

```bash
# 伺服器啟動
uv run start-http      # 啟動 HTTP 伺服器
uv run start-sse       # 啟動 SSE 伺服器

# 開發工具
uv run test            # 執行測試
uv run lint            # 程式碼檢查
uv run format          # 程式碼格式化
uv run typecheck       # 型別檢查

# 配置檢查
uv run config          # 檢查配置
uv run test-config     # 測試伺服器連接
```

### ⚠️ 疑難排解

1. **無效 Token 錯誤**
   - 確保您從 [Superior APIs](https://superiorapis-creator.cteam.com.tw) 取得正確的 token
   - Token 應在客戶端請求中提供，而非在伺服器端設定

2. **埠號被佔用錯誤**
   - 在 `.env` 中更改 `HTTP_SERVER_PORT` 或 `SSE_SERVER_PORT`
   - 或使用 `lsof -i :8000` 檢查埠號使用情況

3. **依賴安裝失敗**
   - 確保已安裝 Python 3.12+：`python --version`
   - 確保已安裝 uv：`uv --version`
   - 虛擬環境問題：在 Windows 上於 cmd/PowerShell 中使用 `rmdir /s /q .venv`，或參考上述 WSL 解決方案
   - 嘗試清除快取：`uv cache clean`

4. **伺服器啟動失敗**
   - 檢查配置：`uv run config`
   - 查看詳細錯誤：在 `.env` 中設定 `LOG_LEVEL=DEBUG`

## 🔌 MCP 客戶端整合

### 多實例部署情境

使用者可能需要配置多個 MCP 伺服器實例，使用不同的 token 來存取不同的 Superior APIs 工具集：

```bash
# 以不同埠號啟動多個伺服器實例
HTTP_SERVER_PORT=8000 uv run start-http &
HTTP_SERVER_PORT=8001 uv run start-http &
SSE_SERVER_PORT=8080 uv run start-sse &
```

### Claude Desktop

使用環境變數配置 MCP 伺服器：

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

### Cursor（SSE 模式）

```bash
# 啟動 SSE 伺服器
uv run start-sse

# Cursor 連接至：http://localhost:8080/sse
```

### HTTP 客戶端

```bash
# 啟動 HTTP 伺服器
uv run start-http

# 發送 JSON-RPC 2.0 請求至：http://localhost:8000/mcp
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## 🛠️ 開發

### 測試

#### 單元測試
```bash
# 執行單元測試（無需啟動伺服器）
uv run test
```

#### 整合測試
```bash
# 先啟動伺服器
uv run start-http &

# 基本功能測試
uv run test-config

# 完整功能測試（需要 Superior APIs token）
uv run test-config --token YOUR_TOKEN

# 檢查配置
uv run test-config --config
```

### 程式碼品質

```bash
# 格式化程式碼
uv run format

# 靜態檢查
uv run lint
uv run typecheck
```

## 📊 架構概覽

### 動態工具生成流程

1. **Token 驗證** → Superior APIs
2. **取得插件列表** → `plugin list`
3. **解析 OpenAPI 規格** → 自動生成 MCP 工具定義
4. **快取工具列表** → 提升效能
5. **處理工具呼叫** → 代理至 Superior APIs

### 支援的 MCP 方法

- `initialize` - 初始化連接
- `tools/list` - 取得可用工具列表
- `tools/call` - 呼叫特定工具

### 錯誤處理

- 網路錯誤自動重試
- Token 驗證失敗時清楚提示
- JSON 解析錯誤詳細記錄
- 完整的 JSON-RPC 2.0 錯誤回應

## 🎯 Dify 整合（最新更新）

### Dify MCP 獨立伺服器

專門為 Dify 1.7.0 MCP 整合設計的特殊伺服器：

```bash
# 啟動 Dify 專用 MCP 伺服器（埠號 9000）
python3 dify_mcp_standalone.py
```

**主要特色：**
- **OpenAPI 格式保留**：維護原始 Superior APIs OpenAPI 結構
- **方法特定解析**：正確處理 GET（parameters 陣列）與 POST（requestBody）
- **Dify 最佳化**：專為 Dify MCP SSE 插件相容性設計
- **增強除錯**：全面記錄以利疑難排解

**配置：**
```json
{
  "name": "Superior APIs",
  "url": "http://your-server:9000/mcp",
  "headers": {
    "token": "your_superior_apis_token"
  }
}
```

**測試：**
```bash
# 測試 Dify MCP 端點
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

**最近修復：**
- ✅ 修復參數解析中的 'properties' 存取錯誤
- ✅ 修正 OpenAPI 路徑結構（`plugin.interface` vs `plugin_item.openapi`）
- ✅ 實作正確的 GET/POST 方法區分
- ✅ 增強參數類型分配（query/path/header/body）

## 🔧 配置選項

完整的配置選項請參考 `.env.example`：

| 變數名稱 | 預設值 | 說明 |
|---------|--------|------|
| `HTTP_SERVER_PORT` | 8000 | HTTP 伺服器埠號 |
| `SSE_SERVER_PORT` | 8080 | SSE 伺服器埠號 |
| `LOG_LEVEL` | INFO | 日誌等級 |
| `DEV_MODE` | false | 開發模式（熱重載） |
| `SERVER_HOST` | 0.0.0.0 | 伺服器主機位址 |
| `CACHE_EXPIRY` | 3600 | 工具快取過期時間（秒） |

**Token 驗證注意事項**：Superior APIs Token 由客戶端在 HTTP 標頭中提供，而非在伺服器端設定。使用 `token: YOUR_TOKEN` 標頭進行驗證。

