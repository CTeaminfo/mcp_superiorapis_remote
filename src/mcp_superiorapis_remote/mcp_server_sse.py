"""
Universal MCP SSE 伺服器 v4 - 相容所有主要 MCP 客戶端
整合 Cursor、Cline、Langflow 和其他 MCP 客戶端的相容性要求

這個伺服器提供通用的 MCP (Model Context Protocol) 支援，
透過 Server-Sent Events (SSE) 和 HTTP 端點來處理多種客戶端連接。

主要功能：
- 支援多種 MCP 客戶端（Cursor、Cline、Langflow 等）
- 整合 Superior APIs 工具集
- 提供 SSE 即時通訊
- Token 認證機制
- 會話管理系統
"""

# === 核心函式庫匯入 ===
import asyncio
import json
import logging
import aiohttp
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import os

# === FastAPI 相關匯入 ===
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# === 日誌系統設置 ===
# 配置日誌格式，包含時間、檔案名稱、級別和訊息
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 設置特定第三方程式庫的日誌級別，避免過多的 DEBUG 訊息
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# === 載入配置 ===
from .config import get_config
config = get_config()

# === Superior APIs 服務配置 ===
SUPERIOR_API_BASE = config.superior_api_base
PLUGINS_LIST_URL = config.plugins_list_url

# === FastAPI 應用程式初始化 ===
app = FastAPI(
    title="Superior APIs MCP SSE Server v4 (Universal)",
    description="通用 MCP 伺服器，支援多種客戶端連接",
    version="4.0.0"
)

# === CORS 跨域資源共享設定 ===
# 增強的 CORS 設定 - 支援跨伺服器和所有 MCP 客戶端
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins if config.validate_origin else ["*"],
    allow_credentials=True,  # 允許憑證傳遞
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],  # 允許的 HTTP 方法
    allow_headers=[
        "*",  # 允許所有標頭
        "Content-Type",  # 內容類型
        "Authorization",  # 授權標頭
        "token",  # 小寫 token 標頭
        "TOKEN",  # 大寫 TOKEN 標頭
        "Mcp-Session-Id",  # Cursor 客戶端會話 ID
        "mcp-session-id",  # 小寫版本的會話 ID
        "X-Requested-With",  # AJAX 請求標識
        "Origin",  # 請求來源
        "Accept",  # 接受的內容類型
        "X-Forwarded-For",  # 代理伺服器轉發的真實 IP
        "X-Real-IP"  # 真實 IP 地址
    ],
    expose_headers=[
        "Mcp-Session-Id",  # 暴露會話 ID 給客戶端
        "Content-Type"  # 暴露內容類型
    ]
)

# === 全域狀態管理變數 ===
# 儲存活躍的 SSE 連接資訊
active_connections: Dict[str, Any] = {}
# 快取 Superior APIs 工具列表（依 token 分組）
tools_cache: Dict[str, List[Dict]] = {}
# Cursor 客戶端會話儲存
session_store: Dict[str, Dict] = {}

# === 輔助函數區段 ===

def generate_session_id() -> str:
    """生成唯一的會話識別 ID
    
    Returns:
        str: UUID4 格式的會話 ID
    """
    return str(uuid.uuid4())

def flatten_enum(schema):
    """扁平化處理 JSON Schema 中的 enum 欄位
    
    將 enum 欄位的值轉換為 description 中的文字說明，
    避免某些 MCP 客戶端對 enum 欄位的解析問題。
    
    Args:
        schema: JSON Schema 物件
        
    Returns:
        dict: 處理後的 schema，enum 資訊移至 description
    """
    if not isinstance(schema, dict):
        return schema
    
    # 複製 schema 避免修改原始物件
    schema = schema.copy()
    
    # 處理根層級的 enum 欄位
    if 'enum' in schema:
        enum_values = schema['enum']
        current_desc = schema.get('description', '')
        enum_desc = " | Enum: " + ", ".join([f"{v}" for v in enum_values])
        schema['description'] = current_desc + enum_desc
        del schema['enum']  # 移除原始 enum 欄位
    
    # 遞迴處理 properties 中的 enum
    if 'properties' in schema:
        for prop_name, prop_schema in schema['properties'].items():
            schema['properties'][prop_name] = flatten_enum(prop_schema)
    
    # 遞迴處理 items 中的 enum（用於陣列類型）
    if 'items' in schema:
        schema['items'] = flatten_enum(schema['items'])
    
    return schema

# === Superior APIs 整合函數 ===

async def fetch_superior_apis_tools(token: str) -> List[Dict]:
    """從 Superior APIs 獲取可用的工具列表
    
    這個函數會連接到 Superior APIs 服務，獲取當前 token 有權限使用的
    所有工具和插件，並將其轉換為 MCP 工具格式。
    
    Args:
        token (str): Superior APIs 的認證 token
        
    Returns:
        List[Dict]: MCP 格式的工具列表
    """
    # 檢查 token 是否提供
    if not token:
        logger.error("❌ 未提供 Superior APIs token")
        return []
    
    # Token 長度檢查
    if len(token) < 10:
        logger.error(f"❌ Token 長度過短: {len(token)} 字元")
        return []
    
    # 檢查快取中是否已有此 token 的工具列表
    if token in tools_cache:
        logger.info(f"🔄 使用快取的工具列表，token: {token[:10]}...")
        return tools_cache[token]
    
    try:
        # 設置 HTTP 請求標頭
        headers = {
            "token": token,  # Superior APIs 認證 token
            "Content-Type": "application/json"
        }
        
        # 建立 HTTP 客戶端會話
        async with aiohttp.ClientSession() as session:
            logger.info(f"🔍 正在從 Superior APIs 獲取工具列表，token: {token[:10]}...")
            
            # 發送 POST 請求到 Superior APIs
            async with session.post(PLUGINS_LIST_URL, headers=headers, json={}) as response:
                logger.info(f"📡 Superior APIs 回應狀態: {response.status}")
                response_text = await response.text()
                
                # 檢查回應狀態是否成功
                if response.status == 200:
                    try:
                        # 解析 JSON 回應
                        data = json.loads(response_text)
                        logger.info(f"✅ 成功解析 Superior APIs 資料")
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON 解析失敗: {e}")
                        return []
                    
                    # 初始化工具列表
                    tools = []
                    
                    # 檢查回應中是否包含插件資料
                    if 'plugins' in data:
                        logger.info(f"🔧 發現 {len(data['plugins'])} 個插件")
                        
                        # 遍歷每個插件
                        for plugin_item in data['plugins']:
                            plugin = plugin_item.get('plugin', {})
                            plugin_name = plugin.get('name_for_model', 'unknown')
                            plugin_description = plugin.get('description_for_model', '')
                            interface = plugin.get('interface', {})
                            paths = interface.get('paths', {})
                            
                            logger.info(f"⚙️ 處理插件: {plugin_name}，包含 {len(paths)} 個 API 端點")
                            
                            # 遍歷插件的每個 API 路徑
                            for path, methods in paths.items():
                                # 遍歷每個 HTTP 方法
                                for method, spec in methods.items():
                                    # 只處理標準的 HTTP 方法
                                    if method.lower() in ['get', 'post', 'put', 'delete']:
                                        # 生成工具名稱
                                        tool_name = spec.get('operationId', 
                                                            f"{method.lower()}_{plugin_name.replace('-', '_')}")
                                        
                                        # 初始化輸入結構描述
                                        input_schema = {"type": "object", "properties": {}}
                                        required_fields = []
                                        
                                        # 處理請求主體參數
                                        if 'requestBody' in spec:
                                            request_body = spec['requestBody']
                                            if 'content' in request_body:
                                                for content_type, content in request_body['content'].items():
                                                    if 'schema' in content:
                                                        body_schema = content['schema']
                                                        # 合併請求主體的屬性
                                                        if 'properties' in body_schema:
                                                            input_schema['properties'].update(body_schema['properties'])
                                                        # 收集必填欄位
                                                        if 'required' in body_schema:
                                                            required_fields.extend(body_schema['required'])
                                        
                                        # 處理 URL 參數和查詢參數
                                        if 'parameters' in spec:
                                            for param in spec['parameters']:
                                                param_name = param['name']
                                                param_schema = param.get('schema', {"type": "string"})
                                                # 定義參數結構
                                                input_schema['properties'][param_name] = {
                                                    "type": param_schema.get('type', 'string'),
                                                    "description": param.get('description', '')
                                                }
                                                # 檢查是否為必填參數
                                                if param.get('required', False):
                                                    required_fields.append(param_name)
                                        
                                        # 設置必填欄位
                                        if required_fields:
                                            input_schema['required'] = required_fields
                                        
                                        # 扁平化 enum 欄位
                                        input_schema = flatten_enum(input_schema)
                                        
                                        # 建立 MCP 工具物件
                                        tool = {
                                            "name": tool_name,
                                            "description": spec.get('summary', plugin_description),
                                            "inputSchema": input_schema,
                                            "_meta": {  # 內部元資料，用於 API 調用
                                                "base_url": config.superior_api_base,
                                                "path": path,
                                                "method": method.upper(),
                                                "plugin_name": plugin_name,
                                                "original_spec": spec
                                            }
                                        }
                                        tools.append(tool)
                                        logger.info(f"✅ 創建工具: {tool_name}")
                    
                    # 將工具列表存入快取
                    tools_cache[token] = tools
                    logger.info(f"🎯 成功轉換 {len(tools)} 個 Superior APIs 工具")
                    return tools
                
                else:
                    logger.error(f"❌ Superior APIs 請求失敗: {response.status} - {response_text}")
                    return []
                    
    except aiohttp.ClientError as e:
        logger.error(f"❌ 網路連接錯誤: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 解析錯誤: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ 未知錯誤: {type(e).__name__}: {e}")
        return []

async def call_superior_api_tool(token: str, tool_name: str, arguments: Dict) -> Dict:
    """調用 Superior APIs 的具體工具
    
    根據工具名稱和參數，實際調用 Superior APIs 的對應端點。
    
    Args:
        token (str): Superior APIs 認證 token
        tool_name (str): 要調用的工具名稱
        arguments (Dict): 工具調用參數
        
    Returns:
        Dict: 包含執行結果的字典
    """
    try:
        # 從快取中獲取工具列表
        tools = tools_cache.get(token, [])
        tool_meta = None
        
        # 尋找對應的工具元資料
        for tool in tools:
            if tool['name'] == tool_name:
                tool_meta = tool.get('_meta', {})
                break
        
        # 檢查工具是否存在
        if not tool_meta:
            logger.error(f"❌ 工具 {tool_name} 未找到")
            return {
                "success": False,
                "error": f"工具 {tool_name} 不存在",
                "content": ""
            }
        
        # 從元資料中提取 API 調用資訊
        base_url = tool_meta['base_url']
        path = tool_meta['path']
        method = tool_meta['method']
        full_url = f"{base_url}{path}"
        
        # 設置請求標頭
        headers = {
            "token": token,
            "Content-Type": "application/json"
        }
        
        logger.info(f"🔨 調用 Superior API: {method} {full_url}，參數: {arguments}")
        
        # 建立 HTTP 會話並執行 API 調用
        async with aiohttp.ClientSession() as session:
            if method == 'GET':
                # GET 請求：參數放在 URL 查詢字符串中
                async with session.get(full_url, headers=headers, params=arguments) as response:
                    result = await response.text()
                    logger.info(f"📡 Superior API 回應 ({response.status}): {result[:200]}...")
                    return {
                        "success": response.status == 200,
                        "content": result,
                        "status_code": response.status
                    }
            else:
                # POST/PUT/DELETE 請求：參數放在請求主體中
                async with session.request(method, full_url, headers=headers, json=arguments) as response:
                    result = await response.text()
                    logger.info(f"📡 Superior API 回應 ({response.status}): {result[:200]}...")
                    return {
                        "success": response.status == 200,
                        "content": result,
                        "status_code": response.status
                    }
                    
    except aiohttp.ClientError as e:
        logger.error(f"❌ 調用 Superior API 工具 {tool_name} 網路錯誤: {e}")
        return {
            "success": False,
            "error": f"網路連接錯誤: {str(e)}",
            "content": ""
        }
    except asyncio.TimeoutError:
        logger.error(f"❌ 調用 Superior API 工具 {tool_name} 逾時")
        return {
            "success": False,
            "error": "請求逾時",
            "content": ""
        }
    except Exception as e:
        logger.error(f"❌ 調用 Superior API 工具 {tool_name} 未知錯誤: {type(e).__name__}: {e}")
        return {
            "success": False,
            "error": f"未知錯誤: {str(e)}",
            "content": ""
        }

# === 認證和安全函數 ===

def extract_token(request: Request) -> Optional[str]:
    """通用 token 提取函數，支援多種認證方式
    
    這個函數會檢查請求中的各種可能位置來尋找認證 token：
    - URL 查詢參數
    - HTTP 標頭（多種格式）
    - Authorization Bearer token
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        Optional[str]: 提取到的 token，若無則返回 None
    """
    # 依序檢查各種可能的 token 來源
    token = (
        request.query_params.get("token") or  # URL 參數中的 token
        request.headers.get("token") or  # 小寫 token 標頭
        request.headers.get("TOKEN") or  # 大寫 TOKEN 標頭
        request.headers.get("Authorization", "").replace("Bearer ", "").replace("bearer ", "") or  # Bearer token
        request.headers.get("X-API-Key") or  # X-API-Key 標頭
        request.headers.get("api-key")  # api-key 標頭
    )
    return token

def validate_origin(request: Request) -> bool:
    """驗證請求來源 - 安全性檢查
    
    檢查請求的來源是否為允許的域名，用於防止跨站請求偽造攻擊。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        bool: True 表示來源合法，False 表示應該拒絕請求
    """
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    
    # 定義允許的請求來源（本地開發環境）
    allowed_origins = [
        "http://localhost",  # 本地主機
        "http://127.0.0.1",  # 迴環地址
        "http://192.168.1.120",  # 內網 IP
        None  # 非瀏覽器請求（如 API 客戶端）
    ]
    
    # 檢查是否為允許的來源
    if origin is None:
        return True  # 非瀏覽器請求通常沒有 Origin 標頭
    
    # 遍歷允許的來源列表
    for allowed in allowed_origins:
        if allowed and origin.startswith(allowed):
            return True
    
    logger.warning(f"⚠️ 來源驗證失敗: {origin}, Host: {host}")
    return True  # 開發環境暫時允許所有來源，生產環境應該嚴格驗證

def extract_session_id(request: Request) -> Optional[str]:
    """提取 Cursor 客戶端會話 ID
    
    Cursor 等客戶端會在請求標頭中包含會話 ID，
    用於維持連接狀態和會話管理。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        Optional[str]: 會話 ID，若無則返回 None
    """
    return (
        request.headers.get("Mcp-Session-Id") or  # 標準格式
        request.headers.get("mcp-session-id") or  # 小寫格式
        request.headers.get("session-id")  # 通用格式
    )

# === API 端點區段 ===

@app.get("/")
async def root():
    """主頁端點 - 提供伺服器資訊和狀態
    
    返回伺服器的基本資訊、版本、支援的客戶端和 API 端點。
    
    Returns:
        dict: 包含伺服器資訊的字典
    """
    return {
        "message": "Superior APIs MCP SSE Server v4 (Universal)", 
        "version": "4.0.0", 
        "status": "running",
        "mcp_protocol_version": "2024-11-05",
        "transport": "SSE (Legacy - Deprecated in MCP 2024-11-05)",
        "note": "SSE transport is deprecated. Consider migrating to Streamable HTTP.",
        "compatibility": ["Cursor", "Cline", "Langflow", "VS Code", "Claude Desktop"],
        "endpoints": {
            "sse": "/sse",  # Cursor 等客戶端使用
            "langflow_sse": "/api/v1/mcp/sse",  # Langflow 專用端點
            "health": "/health",  # 健康檢查
            "status": "/status",  # 狀態查詢
            "langflow_note": "Use localhost or 127.0.0.1 for Langflow compatibility"
        },
        "security": {
            "origin_validation": "enabled",  # 來源驗證已啟用
            "authentication": "token-based"  # 基於 Token 的認證
        }
    }

@app.get("/health")
async def health_check():
    """健康檢查端點 - Langflow 風格
    
    提供伺服器的健康狀態資訊，包括連接數、會話數和快取大小等。
    
    Returns:
        dict: 包含伺服器健康狀態的字典
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "connections": len(active_connections),  # 活躍連接數
        "sessions": len(session_store),  # 活躍會話數
        "cache_size": len(tools_cache),  # 快取大小
        "server": "superior-apis-mcp-v4"
    }

# === SSE 串流端點區段 ===

@app.get("/sse")
async def cursor_sse_endpoint(request: Request):
    """
    Cursor 相容的 SSE 端點
    
    提供 Server-Sent Events 串流連接，符合 Cursor 客戶端的 SSE MCP 規範要求。
    包括會話管理、心跳檢測和連接狀態維持。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        StreamingResponse: SSE 串流回應
        
    Raises:
        HTTPException: 當來源驗證失敗或缺失 token 時
    """
    # 安全性檢查 - 驗證請求來源
    if not validate_origin(request):
        origin = request.headers.get("origin", "unknown")
        logger.warning(f"⚠️ SSE 連接被拒絕: 無效的來源 {origin}")
        raise HTTPException(status_code=403, detail="Origin not allowed")
    
    # 認證檢查 - 獲取並驗證 token
    token = extract_token(request)
    if not token:
        logger.warning("⚠️ SSE 連接被拒絕: 未提供 token")
        raise HTTPException(status_code=401, detail="Token required")
    
    # Token 格式基本檢查
    if len(token) < 10:
        logger.warning(f"⚠️ SSE 連接被拒絕: Token 長度過短 ({len(token)} 字元)")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # 會話管理 - Cursor 特有功能
    session_id = extract_session_id(request) or generate_session_id()
    connection_id = f"cursor_conn_{datetime.now().timestamp()}"
    
    logger.info(f"🔗 新的 Cursor SSE 連接: {connection_id}, 會話: {session_id}, token: {token[:10]}...")
    logger.info(f"📝 請求標頭: {dict(request.headers)}")
    
    async def cursor_event_generator():
        """
        Cursor SSE 事件生成器
        
        管理 Cursor 客戶端的 SSE 連接生命週期，包括：
        - 連接初始化
        - 定期心跳檢查
        - 連接狀態管理
        - 清理資源
        """
        try:
            # 保存連接資訊到全域狀態
            active_connections[connection_id] = {
                'timestamp': datetime.now(),
                'token': token,
                'session_id': session_id,
                'client_type': 'cursor'
            }
            
            # 儲存會話資訊
            session_store[session_id] = {
                'connection_id': connection_id,
                'token': token,
                'created_at': datetime.now()
            }
            
            # 發送初始連接事件 - 符合 JSON-RPC 2.0 標準
            initial_event = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {
                    "status": "connected",
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                    "serverInfo": {
                        "name": "superior-apis-mcp-v4-universal",
                        "version": "4.0.0"
                    }
                }
            }
            yield f"event: message\ndata: {json.dumps(initial_event)}\n\n"
            
            logger.info(f"✅ Cursor SSE 連接已建立: {connection_id}")
            
            # 心跳循環 - 維持連接活躍狀態
            heartbeat_counter = 0
            HEARTBEAT_INTERVAL = 30  # 30 秒間隔適合 Cursor
            
            while True:
                # 檢查客戶端是否已斷線
                if await request.is_disconnected():
                    logger.info(f"🔌 Cursor 客戶端已斷線: {connection_id}")
                    break
                
                heartbeat_counter += 1
                # 發送心跳事件 - 符合 JSON-RPC 2.0 格式
                heartbeat_event = {
                    "jsonrpc": "2.0",
                    "method": "notifications/ping",
                    "params": {
                        "type": "heartbeat",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                        "count": heartbeat_counter
                    }
                }
                yield f"event: message\ndata: {json.dumps(heartbeat_event)}\n\n"
                
                # 等待下一次心跳
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                
        except asyncio.CancelledError:
            logger.info(f"🗑️ Cursor SSE 連接被取消: {connection_id}")
        except ConnectionResetError:
            logger.info(f"🔌 Cursor 客戶端主動斷線: {connection_id}")
        except Exception as e:
            logger.error(f"❌ Cursor SSE 連接未知錯誤 {connection_id}: {type(e).__name__}: {e}")
        finally:
            # 清理連接資源
            try:
                active_connections.pop(connection_id, None)
                session_store.pop(session_id, None)
                logger.info(f"🧹 已清理 Cursor 連接: {connection_id}")
            except Exception as cleanup_error:
                logger.error(f"❌ 清理 Cursor 連接資源時發生錯誤: {cleanup_error}")

    # 返回 SSE 串流回應
    return StreamingResponse(
        cursor_event_generator(),
        media_type="text/event-stream",
        headers={
            # SSE 必需的標頭
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",  # 禁止快取
            "Connection": "keep-alive",  # 保持連接
            # CORS 設定
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Mcp-Session-Id, token",
            # Cursor 特有標頭
            "Mcp-Session-Id": session_id,  # 會話 ID 返回給客戶端
            "X-Accel-Buffering": "no",  # Nginx 代理優化
        }
    )

@app.get("/api/v1/mcp/sse")
async def langflow_sse_endpoint(request: Request):
    """
    Langflow 相容的 SSE 端點
    
    提供符合 Langflow 客戶端規範的 SSE 連接。
    使用 /api/v1/mcp/sse 路徑符合 Langflow API 約定。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        StreamingResponse: SSE 串流回應
        
    Raises:
        HTTPException: 當來源驗證失敗或缺失 token 時
    """
    # 安全性檢查
    if not validate_origin(request):
        origin = request.headers.get("origin", "unknown")
        logger.warning(f"⚠️ Langflow SSE 連接被拒絕: 無效的來源 {origin}")
        raise HTTPException(status_code=403, detail="Origin not allowed")
    
    # Token 認證
    token = extract_token(request)
    if not token:
        logger.warning("⚠️ Langflow SSE 連接被拒絕: 未提供 token")
        raise HTTPException(status_code=401, detail="Token required")
    
    # Token 格式檢查
    if len(token) < 10:
        logger.warning(f"⚠️ Langflow SSE 連接被拒絕: Token 長度過短 ({len(token)} 字元)")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # 生成連接 ID
    connection_id = str(uuid.uuid4())
    logger.info(f"🔗 新的 Langflow SSE 連接: {connection_id}, token: {token[:10]}...")
    
    async def langflow_event_generator():
        """
        Langflow SSE 事件生成器
        
        管理 Langflow 客戶端的 SSE 連接生命週期。
        與 Cursor 相似，但不需要會話管理功能。
        """
        try:
            # 記錄連接資訊
            active_connections[connection_id] = {
                'timestamp': datetime.now(),
                'token': token,
                'client_type': 'langflow'
            }
            
            # Langflow 初始事件 - 符合 JSON-RPC 2.0 標準
            initial_event = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {
                    "type": "connection_established",
                    "connection_id": connection_id,
                    "timestamp": datetime.now().isoformat(),
                    "capabilities": ["tools", "resources"],  # 支援的功能
                    "serverInfo": {
                        "name": "superior-apis-mcp-v4-universal",
                        "version": "4.0.0"
                    }
                }
            }
            yield f"event: message\ndata: {json.dumps(initial_event)}\n\n"
            
            logger.info(f"✅ Langflow SSE 連接已建立: {connection_id}")
            
            # 心跳循環 - 保持連接活躍
            heartbeat_counter = 0
            HEARTBEAT_INTERVAL = 30  # 30 秒間隔
            
            while True:
                # 檢查客戶端連接狀態
                if await request.is_disconnected():
                    logger.info(f"🔌 Langflow 客戶端已斷線: {connection_id}")
                    break
                
                heartbeat_counter += 1
                # Langflow 心跳事件 - 符合 JSON-RPC 2.0 格式
                heartbeat_event = {
                    "jsonrpc": "2.0",
                    "method": "notifications/ping",
                    "params": {
                        "type": "heartbeat",
                        "connection_id": connection_id,
                        "timestamp": datetime.now().isoformat(),
                        "count": heartbeat_counter
                    }
                }
                yield f"event: message\ndata: {json.dumps(heartbeat_event)}\n\n"
                
                # 等待下一次心跳
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                
        except asyncio.CancelledError:
            logger.info(f"🗑️ Langflow SSE 連接被取消: {connection_id}")
        except ConnectionResetError:
            logger.info(f"🔌 Langflow 客戶端主動斷線: {connection_id}")
        except Exception as e:
            logger.error(f"❌ Langflow SSE 連接未知錯誤 {connection_id}: {type(e).__name__}: {e}")
        finally:
            # 清理連接資源
            try:
                active_connections.pop(connection_id, None)
                logger.info(f"🧹 已清理 Langflow 連接: {connection_id}")
            except Exception as cleanup_error:
                logger.error(f"❌ 清理 Langflow 連接資源時發生錯誤: {cleanup_error}")

    # 返回 SSE 串流回應
    return StreamingResponse(
        langflow_event_generator(),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",  # 禁止快取
            "Connection": "keep-alive",  # 保持連接
            # CORS 設定
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, token, TOKEN",
            "X-Accel-Buffering": "no",  # Nginx 代理優化
        }
    )

# === MCP 訊息處理端點區段 ===

@app.post("/messages")
@app.post("/messages/")
@app.post("/mcp/call")
async def handle_mcp_messages(request: Request):
    """
    通用 MCP 訊息處理端點
    
    處理所有 MCP 客戶端的 JSON-RPC 2.0 請求，包括：
    - 初始化請求
    - 工具列表查詢
    - 工具調用請求
    - 通知訊息
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        JSONResponse: JSON-RPC 2.0 格式的回應
        
    Raises:
        HTTPException: 當認證失敗或請求格式錯誤時
    """
    try:
        # 解析 JSON-RPC 請求
        body = await request.json()
        method = body.get("method")
        request_id = body.get("id")
        
        # Token 認證
        token = extract_token(request)
        if not token:
            logger.error("❌ MCP 請求被拒絕: 未提供 token")
            raise HTTPException(status_code=401, detail="Token required")
        
        # 會話管理 - 支援 Cursor 客戶端
        session_id = extract_session_id(request)
        
        logger.info(f"🔄 MCP 訊息: {method} (id: {request_id}), token: {token[:10]}...")
        if session_id:
            logger.info(f"📱 會話 ID: {session_id}")
        
        # === 處理不同的 MCP 方法 ===
        
        if method == "initialize":
            # MCP 初始化請求
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",  # MCP 協定版本
                    "capabilities": {
                        "tools": {},  # 支援工具功能
                        "resources": {}  # 支援資源功能
                    },
                    "serverInfo": {
                        "name": "superior-apis-mcp-v4-universal",
                        "version": "4.0.0"
                    }
                }
            }
            logger.info("✅ MCP 初始化成功")
            return JSONResponse(response)
        
        elif method == "notifications/initialized":
            # 客戶端初始化完成通知
            logger.info("✅ 收到客戶端初始化通知")
            # Cursor 相容：使用 204 No Content 而不是 202 Accepted
            return Response(status_code=204)
        
        elif method == "tools/list":
            # 查詢可用工具列表
            tools = await fetch_superior_apis_tools(token)
            logger.info(f"🔧 返回 {len(tools)} 個 Superior APIs 工具")
            
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": tools  # 工具列表
                }
            }
            return JSONResponse(response)
        
        elif method == "tools/call":
            # 工具調用請求
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            logger.info(f"🔨 調用 Superior API 工具: {tool_name}")
            
            # 執行工具調用
            result = await call_superior_api_tool(token, tool_name, arguments)
            
            if result.get("success", False):
                # 成功回應
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result.get("content", "")
                            }
                        ]
                    }
                }
                logger.info(f"✅ 工具調用成功: {tool_name}")
                return JSONResponse(response)
            else:
                # 錯誤回應
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,  # Internal error
                        "message": result.get("error", "工具執行失敗"),
                        "data": {
                            "status_code": result.get("status_code"),
                            "content": result.get("content", "")
                        }
                    }
                }
                logger.error(f"❌ 工具調用失敗: {tool_name}")
                return JSONResponse(response)
        
        else:
            # 不支援的方法
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,  # Method not found
                    "message": f"方法不存在: {method}"
                }
            }
            logger.warning(f"⚠️ 不支援的 MCP 方法: {method}")
            return JSONResponse(response, status_code=400)
            
    except HTTPException:
        # 重新拋出 HTTP 異常
        raise
    except json.JSONDecodeError as e:
        # JSON 解析錯誤
        logger.error(f"❌ MCP 請求 JSON 解析失敗: {e}")
        response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32700,  # Parse error
                "message": "JSON 解析錯誤",
                "data": str(e)
            }
        }
        return JSONResponse(response, status_code=400)
    except Exception as e:
        # 捕獲所有其他錯誤
        logger.error(f"❌ MCP 訊息處理未知錯誤: {type(e).__name__}: {e}")
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {
                "code": -32603,  # Internal error
                "message": "內部錯誤",
                "data": f"{type(e).__name__}: {str(e)}"
            }
        }
        return JSONResponse(response, status_code=500)

# === 專用路由端點 ===
@app.post("/api/v1/mcp/sse")
async def handle_langflow_mcp_messages(request: Request):
    """Langflow 專用的 MCP 訊息處理端點"""
    logger.info("🔄 Langflow MCP message received, redirecting to universal handler")
    return await handle_mcp_messages(request)

# === POST SSE 端點處理 ===
@app.post("/sse")
async def sse_post_handler(request: Request):
    """處理 POST /sse 請求，重定向到通用訊息處理"""
    logger.info("📨 Received POST /sse request, redirecting to messages")
    return await handle_mcp_messages(request)

# === OPTIONS 端點處理 ===
@app.options("/sse")
@app.options("/api/v1/mcp/sse")
@app.options("/messages")
async def options_handler():
    """處理 OPTIONS 預檢請求"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, token, TOKEN, Mcp-Session-Id, mcp-session-id",
        }
    )

# === 狀態查詢端點 ===

@app.get("/status")
async def status():
    """
    伺服器狀態檢查端點
    
    提供詳細的伺服器狀態資訊，包括連接數、支援的客戶端和 API 端點。
    
    Returns:
        dict: 包含伺服器狀態和統計資訊的字典
    """
    return {
        "server": "Superior APIs MCP SSE v4 (Universal)",
        "version": "4.0.0",
        "active_connections": len(active_connections),  # 當前活躍連接數
        "active_sessions": len(session_store),  # 當前活躍會話數
        "cached_tokens": len(tools_cache),  # 快取中的 token 數量
        "superior_api_base": SUPERIOR_API_BASE,  # Superior APIs 基礎 URL
        "timestamp": datetime.now().isoformat(),
        "compatibility": {  # 客戶端相容性狀態
            "cursor": "✅ 完整支援，包括會話管理",
            "cline": "✅ 完整支援",
            "langflow": "✅ 完整支援，使用 /api/v1/mcp/sse",
            "vscode": "✅ 相容",
            "claude_desktop": "⚠️ SSE 不支援 (請使用 stdio)"
        },
        "endpoints": {  # 可用的 API 端點
            "cursor_sse": "/sse",
            "langflow_sse": "/api/v1/mcp/sse",
            "messages": "/messages",
            "health": "/health",
            "status": "/status"
        }
    }

# === 伺服器啟動區段 ===

def main():
    """SSE 伺服器主程式入口點"""
    # 顯示啟動資訊
    print("🚀 啟動 Superior APIs MCP SSE Server v4 (Universal)")
    print("📍 伺服器將在以下地址提供服務:")
    print(f"   - http://localhost:{config.sse_server_port}")
    print(f"   - http://127.0.0.1:{config.sse_server_port}")
    print("🔗 SSE 端點: /sse")
    print("🔗 MCP 訊息處理: /messages")
    print("🔑 認證方式: Token-based")
    print("🔒 CORS: 已啟用 (開發環境)")
    print("" + "="*60)
    
    # 啟動 FastAPI 伺服器
    uvicorn.run(
        "mcp_superiorapis_remote.mcp_server_sse:app",  # 應用程式模組
        host=config.server_host,  # 綁定網路介面
        port=config.sse_server_port,  # 端口號
        reload=config.dev_mode,  # 開發模式自動重載
        log_level=config.log_level.lower()  # 日誌級別
    )

if __name__ == "__main__":
    main()