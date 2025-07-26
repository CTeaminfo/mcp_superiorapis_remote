# MCP JSON-RPC 2.0 規範範例與說明

## 📋 目錄
1. [基本格式規範](#基本格式規範)
2. [初始化流程](#初始化流程)
3. [工具列表查詢](#工具列表查詢)
4. [工具呼叫](#工具呼叫)
5. [錯誤處理](#錯誤處理)
6. [OpenAPI 參數格式](#openapi-參數格式)
7. [實際測試範例](#實際測試範例)

---

## 基本格式規範

### JSON-RPC 2.0 基本結構
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": {}
}
```

### 成功回應格式
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    // 回應內容
  }
}
```

### 錯誤回應格式
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found"
  }
}
```

---

## 初始化流程

### 1. 客戶端發送初始化請求
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

### 2. 伺服器回應
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "capabilities": {
      "tools": {
        "listChanged": true
      }
    },
    "serverInfo": {
      "name": "Dify MCP Standalone Server",
      "version": "1.0.0"
    },
    "protocolVersion": "2024-11-05"
  }
}
```

### 3. 客戶端發送初始化完成通知
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized",
  "params": {}
}
```

---

## 工具列表查詢

### 請求
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

### 回應範例
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "get_popular_news",
        "description": "讓使用者能夠迅速瀏覽最受關注的新聞",
        "inputSchema": {
          "summary": "讓使用者能夠迅速瀏覽最受關注的新聞",
          "parameters": []
        }
      },
      {
        "name": "post_stock_details",
        "description": "查詢股票個股資訊",
        "inputSchema": {
          "summary": "查詢股票個股資訊",
          "requestBody": {
            "description": "提供一個包含股票代號的JSON物件",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "symbol": {
                      "description": "股票代號，如:0050.TW",
                      "type": "string"
                    }
                  },
                  "required": ["symbol"]
                }
              }
            }
          }
        }
      }
    ]
  }
}
```

---

## 工具呼叫

### GET 方法工具呼叫（無參數）
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_popular_news",
    "arguments": {}
  }
}
```

### GET 方法工具呼叫（有參數）
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "get_sms_send_otp",
    "arguments": {
      "sid": "abc123",
      "otp_code": "456789"
    }
  }
}
```

### POST 方法工具呼叫
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "post_stock_details",
    "arguments": {
      "symbol": "0050.TW"
    }
  }
}
```

### 工具呼叫成功回應
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\\n  \\\"status\\\": \\\"success\\\",\\n  \\\"data\\\": {\\n    \\\"symbol\\\": \\\"0050.TW\\\",\\n    \\\"name\\\": \\\"元大台灣50\\\",\\n    \\\"price\\\": 142.50\\n  }\\n}"
      }
    ]
  }
}
```

---

## 錯誤處理

### 常見錯誤代碼

| 錯誤代碼 | 說明 | 範例 |
|---------|------|------|
| -32600 | Invalid Request | 請求格式錯誤 |
| -32601 | Method not found | 方法不存在 |
| -32602 | Invalid params | 參數錯誤 |
| -32603 | Internal error | 內部錯誤 |
| 401 | Unauthorized | Token 驗證失敗 |

### 錯誤回應範例
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Missing tool name"
  }
}
```

### Token 錯誤
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": 401,
    "message": "Token required. Please provide token in headers."
  }
}
```

---

## OpenAPI 參數格式

### GET 方法 - Parameters 陣列格式
```json
{
  "name": "get_mail_send_otp",
  "description": "郵件驗證 OTP",
  "inputSchema": {
    "summary": "郵件驗證 OTP",
    "parameters": [
      {
        "name": "sid",
        "alias": "SID",
        "in": "query",
        "required": true,
        "description": "安全識別符",
        "schema": {
          "type": "string"
        }
      },
      {
        "name": "otp_code",
        "alias": "OTP 驗證碼",
        "in": "query",
        "required": true,
        "description": "OTP 驗證碼",
        "schema": {
          "type": "string"
        }
      }
    ]
  }
}
```

### POST 方法 - RequestBody 格式
```json
{
  "name": "post_mail_send_otp",
  "description": "郵件寄送 OTP",
  "inputSchema": {
    "summary": "郵件寄送 OTP",
    "requestBody": {
      "description": "requestBody description",
      "content": {
        "application/json": {
          "schema": {
            "description": "API Request Body參數",
            "type": "object",
            "required": ["email", "company_name"],
            "properties": {
              "email": {
                "description": "電子郵件格式",
                "type": "string"
              },
              "company_name": {
                "description": "服務名稱",
                "type": "string"
              },
              "otp_valid_time": {
                "description": "OTP 驗證碼的有效時間",
                "type": "integer"
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 實際測試範例

### 測試伺服器健康狀態
```bash
curl http://localhost:9000/health
```

### 測試工具列表（需要 token）
```bash
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }'
```

### 測試工具呼叫 - GET 方法
```bash
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "get_popular_news",
      "arguments": {}
    }
  }'
```

### 測試工具呼叫 - POST 方法
```bash
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "post_stock_details",
      "arguments": {
        "symbol": "0050.TW"
      }
    }
  }'
```

### 測試錯誤處理 - 無效方法
```bash
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "token: YOUR_SUPERIOR_APIS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "invalid/method",
    "params": {}
  }'
```

---

## 🔧 開發注意事項

### 1. **Token 驗證**
- 所有 MCP 請求都必須包含有效的 Superior APIs token
- Token 可通過以下方式提供：
  - HTTP Header: `token: YOUR_TOKEN`
  - Authorization Header: `Authorization: Bearer YOUR_TOKEN`
  - URL 參數: `?token=YOUR_TOKEN`

### 2. **參數處理規則**
- **GET/DELETE 方法**：參數放在 `parameters` 陣列中，根據 `in` 欄位分配到 query/path/header
- **POST/PUT/PATCH 方法**：參數放在 `requestBody` 中，全部作為 JSON body 發送

### 3. **回應格式**
- 工具呼叫的結果統一包裝在 `content` 陣列中
- 每個內容項目包含 `type: "text"` 和 `text` 欄位
- JSON 結果會被序列化為字串

### 4. **錯誤處理**
- 網路錯誤、API 錯誤、參數錯誤都會返回適當的 JSON-RPC 2.0 錯誤格式
- 錯誤代碼遵循 JSON-RPC 2.0 標準

### 5. **快取機制**
- 工具列表會按 token 快取 5 分鐘（可調整）
- 提供 `/clear-cache` 端點手動清除快取
- 提供 `/cache-status` 端點查看快取狀態

---

## 📚 相關資源

- [JSON-RPC 2.0 規範](https://www.jsonrpc.org/specification)
- [MCP 協定規範](https://modelcontextprotocol.io/docs/concepts/tools)
- [OpenAPI 3.1.1 規範](https://swagger.io/specification/)
- [Dify MCP 插件文檔](https://docs.dify.ai/guides/tools/tool-configuration/mcp)

---

## 🚀 快速開始

1. **啟動伺服器**：
   ```bash
   python3 dify_mcp_standalone.py
   ```

2. **配置 Dify MCP**：
   ```json
   {
     "name": "Superior APIs",
     "url": "http://your-server:9000/mcp",
     "headers": {
       "token": "your_superior_apis_token"
     }
   }
   ```

3. **測試連接**：
   ```bash
   curl -X POST http://localhost:9000/mcp \
     -H "Content-Type: application/json" \
     -H "token: YOUR_TOKEN" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   ```

現在您已經掌握了完整的 MCP JSON-RPC 2.0 規範，可以開始實作自己的 MCP 工具了！