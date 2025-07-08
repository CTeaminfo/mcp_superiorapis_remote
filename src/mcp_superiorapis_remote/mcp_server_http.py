"""
Superior APIs MCP Streamable HTTP Server v3 - 符合 MCP 官方規範

實作 MCP Streamable HTTP 傳輸協定，支援 JSON-RPC 2.0 和 Superior APIs 整合。
根據 MCP 官方規範 (2025-03-26) 實作：

主要特色：
- 單一 /mcp 端點支援 POST/GET 方法
- JSON-RPC 2.0 訊息格式
- 支援 MCP 標準方法: initialize, tools/list, tools/call
- Mcp-Session-Id 會話管理
- 透過 header token 查詢 Superior APIs list_v3
- 可選的 SSE 支援 (本實作中使用純 HTTP)

參考文件：
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- JSON-RPC 2.0 Specification
"""

# === 核心函式庫匯入 ===
# Python 標準庫
import asyncio          # 非同步程式設計支援
import json             # JSON 資料處理
import uuid             # 唯一識別碼生成
from datetime import datetime  # 日期時間處理
from typing import Any, Dict, Optional, List  # 型別提示

# 第三方函式庫
import aiohttp          # 非同步 HTTP 客戶端

# === FastAPI 框架相關匯入 ===
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware  # 跨域資源共享中介軟體
from fastapi.responses import JSONResponse         # JSON 回應格式
from pydantic import BaseModel                     # 資料驗證模型
import uvicorn                                     # ASGI 伺服器
import logging                                     # 日誌記錄系統

# === 日誌系統設置 ===
# 配置基本的日誌格式和級別（將在載入配置後再次調整）
logging.basicConfig(
    level=logging.INFO,                                          # 設定日誌級別為 INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # 日誌格式：時間-模組-級別-訊息
    datefmt='%Y-%m-%d %H:%M:%S'                                 # 時間格式：年-月-日 時:分:秒
)
logger = logging.getLogger(__name__)  # 獲取當前模組的日誌記錄器

# === 載入配置 ===
from .config import get_config
config = get_config()

# 根據配置調整日誌級別
logging.getLogger().setLevel(getattr(logging, config.log_level.upper()))
# 調整第三方程式庫的日誌級別，避免過多的 DEBUG 訊息
logging.getLogger("aiohttp").setLevel(logging.WARNING)        # aiohttp 只顯示警告以上級別
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # uvicorn 存取日誌只顯示警告以上級別

# === Superior APIs 服務配置 ===
SUPERIOR_API_BASE = config.superior_api_base
PLUGINS_LIST_URL = config.plugins_list_url

# === 全域狀態管理變數 ===
# 這些變數用於管理伺服器的全域狀態
tools_cache: Dict[str, List[Dict]] = {}        # 工具快取：依 token 分組儲存 Superior APIs 工具列表
session_store: Dict[str, Dict] = {}            # MCP 會話儲存：追蹤每個會話的狀態和資訊
active_connections: Dict[str, Any] = {}        # WebSocket 連線記錄：兼容性功能，記錄活躍連線

# === FastAPI 應用程式初始化 ===
app = FastAPI(
    title="Superior APIs MCP Streamable HTTP Server",
    description="符合 MCP 官方規範的 Streamable HTTP 伺服器，支援 JSON-RPC 2.0 和 Superior APIs 整合",
    version="3.0.0"
)

# === CORS 跨域資源共享設定 ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins if config.validate_origin else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD", "DELETE"],
    allow_headers=[
        "*",
        "Content-Type",
        "Authorization",
        "Accept",  # MCP 規範要求
        "token",  # Superior APIs token
        "TOKEN",
        "Mcp-Session-Id",  # MCP 會話 ID
        "mcp-session-id",
        "X-API-Key",
        "api-key"
    ],
    expose_headers=[
        "Mcp-Session-Id",  # 返回會話 ID 給客戶端
        "Content-Type"
    ]
)


# === MCP 資料模型定義 ===

class MCPRequest(BaseModel):
    """
    MCP JSON-RPC 2.0 請求模型
    
    定義符合 JSON-RPC 2.0 規範的 MCP 請求格式。
    支援以下標準 MCP 方法：
    - initialize: 初始化 MCP 連線
    - tools/list: 獲取可用工具列表  
    - tools/call: 調用特定工具
    
    範例請求：
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    """
    jsonrpc: str = "2.0"                           # JSON-RPC 協定版本，固定為 "2.0"
    id: Optional[Any] = None                       # 請求識別碼，可為數字、字串或 null
    method: str                                    # 要調用的方法名稱
    params: Optional[Dict[str, Any]] = None        # 方法參數，可選

# === 兼容性 REST API 模型 ===
# 這些模型保留用於向後兼容，支援舊版 REST API 端點

class ToolCallRequest(BaseModel):
    """工具調用請求的資料模型（兼容性 REST API）
    
    用於 /call 端點的舊版 REST API 格式。
    MCP 客戶端應使用 /mcp 端點的 tools/call 方法。
    """
    name: str                                      # 要調用的工具名稱
    arguments: Optional[Dict[str, Any]] = None     # 工具調用參數，可選


class ToolCallResponse(BaseModel):
    """工具調用回應的資料模型（兼容性 REST API）
    
    /call 端點的回應格式，包含執行結果和時間戳。
    """
    success: bool                              # 執行是否成功
    content: str                               # 工具執行的回應內容
    error: Optional[str] = None                # 錯誤訊息（失敗時提供）
    timestamp: str                             # 執行時間戳記（ISO 格式）


class ToolInfo(BaseModel):
    """工具資訊的資料模型（兼容性 REST API）
    
    /tools 端點的回應格式，描述每個可用工具的詳細資訊。
    """
    name: str                                  # 工具的唯一名稱
    description: str                           # 工具功能描述
    schema: Dict[str, Any]                     # JSON Schema 格式的參數定義
    method: str                                # HTTP 方法（GET、POST 等）
    path: str                                  # Superior APIs 的 API 路徑


class WebSocketConnection:
    """WebSocket 連線管理類別（兼容性功能）
    
    管理單一 WebSocket 連線的狀態和操作。
    提供訊息發送和連線關閉功能。
    注意：這是兼容性功能，MCP 客戶端建議使用 /mcp 端點。
    """
    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket                 # WebSocket 連線物件
        self.client_id = client_id                 # 客戶端唯一識別碼
        self.connected = True                      # 連線狀態標記

    async def send_message(self, message: dict):
        """發送 JSON 訊息給 WebSocket 客戶端
        
        Args:
            message (dict): 要發送的訊息字典
        """
        try:
            # 將字典轉換為 JSON 字串並發送，確保中文字元正確顯示
            await self.websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.error(f"📤 發送 WebSocket 訊息失敗: {e}")
            self.connected = False  # 標記連線為斷開狀態

    async def close(self):
        """安全關閉 WebSocket 連線"""
        self.connected = False  # 先標記為斷開狀態
        try:
            await self.websocket.close()  # 嘗試正常關閉連線
        except Exception as e:
            logger.error(f"🔌 關閉 WebSocket 連線失敗: {e}")


# === WebSocket 連線管理器 ===
class ConnectionManager:
    """管理所有 WebSocket 連線的類別（兼容性功能）
    
    負責 WebSocket 連線的建立、斷開和廣播功能。
    維護所有活躍連線的清單並提供群組操作。
    """
    
    def __init__(self):
        self.active_connections: List[WebSocketConnection] = []  # 活躍連線清單

    async def connect(self, websocket: WebSocket, client_id: str):
        """接受新的 WebSocket 連線"""
        await websocket.accept()
        connection = WebSocketConnection(websocket, client_id)
        self.active_connections.append(connection)
        logger.info(f"客戶端 {client_id} 已連線")
        return connection

    def disconnect(self, connection: WebSocketConnection):
        """斷開 WebSocket 連線"""
        if connection in self.active_connections:
            self.active_connections.remove(connection)
            logger.info(f"客戶端 {connection.client_id} 已斷線")

    async def broadcast(self, message: dict):
        """廣播訊息給所有連線的客戶端"""
        disconnected = []
        for connection in self.active_connections:
            if connection.connected:
                await connection.send_message(message)
            else:
                disconnected.append(connection)
        
        # 清理已斷線的連線
        for conn in disconnected:
            self.disconnect(conn)


# 創建連線管理器實例
manager = ConnectionManager()


# === 輔助函數區段 ===

def extract_token(request: Request) -> Optional[str]:
    """通用 token 提取函數，支援多種認證方式
    
    這個函數會檢查請求中的各種可能位置來尋找認證 token。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        Optional[str]: 提取到的 token，若無則返回 None
    """
    token = (
        request.query_params.get("token") or  # URL 參數中的 token
        request.headers.get("token") or  # 小寫 token 標頭
        request.headers.get("TOKEN") or  # 大寫 TOKEN 標頭
        request.headers.get("Authorization", "").replace("Bearer ", "").replace("bearer ", "") or  # Bearer token
        request.headers.get("X-API-Key") or  # X-API-Key 標頭
        request.headers.get("api-key")  # api-key 標頭
    )
    return token

def extract_session_id(request: Request) -> Optional[str]:
    """提取 MCP 會話 ID
    
    根據 MCP Streamable HTTP 規範，客戶端可以在 Mcp-Session-Id header 中提供會話 ID。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        Optional[str]: 會話 ID，若無則返回 None
    """
    return (
        request.headers.get("Mcp-Session-Id") or
        request.headers.get("mcp-session-id")
    )

def generate_session_id() -> str:
    """生成新的 MCP 會話 ID
    
    Returns:
        str: 新的 UUID 格式會話 ID
    """
    return str(uuid.uuid4())

def validate_origin(request: Request) -> bool:
    """驗證請求來源 - MCP 安全性要求
    
    根據 MCP 規範，伺服器必須驗證 Origin header。
    
    Args:
        request (Request): FastAPI 請求物件
        
    Returns:
        bool: True 表示來源合法
    """
    origin = request.headers.get("origin")
    
    # 允許的來源（開發環境）
    allowed_origins = [
        "http://localhost",
        "http://127.0.0.1",
        "http://192.168.1.120",
        None  # 非瀏覽器請求
    ]
    
    if origin is None:
        return True  # 非瀏覽器請求
    
    for allowed in allowed_origins:
        if allowed and origin.startswith(allowed):
            return True
    
    logger.warning(f"⚠️ 來源驗證失敗: {origin}")
    return True  # 開發環境暫時允許

# === JSON-RPC 2.0 輔助函數 ===

def create_jsonrpc_response(request_id: Any, result: Any) -> Dict[str, Any]:
    """建立 JSON-RPC 2.0 成功回應
    
    Args:
        request_id: 請求 ID
        result: 回應結果
        
    Returns:
        Dict: JSON-RPC 2.0 回應物件
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }

def create_jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    """建立 JSON-RPC 2.0 錯誤回應
    
    Args:
        request_id: 請求 ID
        code: 錯誤代碼
        message: 錯誤訊息
        data: 額外錯誤資料
        
    Returns:
        Dict: JSON-RPC 2.0 錯誤回應物件
    """
    error_obj = {
        "code": code,
        "message": message
    }
    if data is not None:
        error_obj["data"] = data
    
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error_obj
    }

def flatten_enum(schema):
    """扁平化處理 JSON Schema 中的 enum 欄位
    
    與 sse_server_v4_universal.py 中的函數相同，
    將 enum 欄位的值轉換為 description 中的文字說明。
    """
    if not isinstance(schema, dict):
        return schema

    schema = schema.copy()
    properties = schema.get('properties', {})

    for prop_name, prop in properties.items():
        if prop.get('type') == 'object':
            schema['properties'][prop_name] = flatten_enum(prop)

        elif prop.get('type') == 'array':
            items = prop.get('items', {})
            if 'enum' in items:
                enum_val = items['enum']
                original_desc = prop.get('description', '')

                if isinstance(enum_val, dict):
                    enum_str = ', '.join(f"{k}: {v}" for k, v in enum_val.items())
                    prop['description'] = f"{original_desc} | Enum: {enum_str}"
                elif isinstance(enum_val, list):
                    enum_str = ', '.join(str(e) for e in enum_val)
                    prop['description'] = f"{original_desc} | 選項: {enum_str}"

                prop['items'].pop('enum', None)

            if isinstance(items, dict):
                prop['items'] = flatten_enum(items)

        if 'enum' in prop:
            enum_val = prop['enum']
            original_desc = prop.get('description', '')

            if isinstance(enum_val, dict):
                enum_str = ', '.join(f"{k}: {v}" for k, v in enum_val.items())
                prop['description'] = f"{original_desc} | Enum: {enum_str}"
            elif isinstance(enum_val, list):
                enum_str = ', '.join(str(e) for e in enum_val)
                prop['description'] = f"{original_desc} | 選項: {enum_str}"

            prop.pop('enum')

    return schema


# === Superior APIs 整合函數 ===

async def fetch_superior_apis_tools(token: str) -> List[Dict]:
    """從 Superior APIs 獲取可用的工具列表
    
    與 sse_server_v4_universal.py 保持一致的實現，
    支援快取機制和詳細的錯誤處理。
    
    Args:
        token (str): Superior APIs 的認證 token
        
    Returns:
        List[Dict]: MCP 格式的工具列表
    """
    if not token:
        logger.error("❌ 未提供 Superior APIs token")
        return []
    
    if len(token) < 10:
        logger.error(f"❌ Token 長度過短: {len(token)} 字元")
        return []
    
    # 檢查快取
    if token in tools_cache:
        logger.info(f"🔄 使用快取的工具列表，token: {token[:10]}...")
        return tools_cache[token]
    
    try:
        headers = {
            "token": token,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            logger.info(f"🔍 正在從 Superior APIs 獲取工具列表，token: {token[:10]}...")
            
            async with session.post(PLUGINS_LIST_URL, headers=headers, json={}) as response:
                logger.info(f"📡 Superior APIs 回應狀態: {response.status}")
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        logger.info(f"✅ 成功解析 Superior APIs 資料")
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON 解析失敗: {e}")
                        return []
                    
                    tools = []
                    
                    if 'plugins' in data:
                        logger.info(f"🔧 發現 {len(data['plugins'])} 個插件")
                        
                        for plugin_item in data['plugins']:
                            plugin = plugin_item.get('plugin', {})
                            plugin_name = plugin.get('name_for_model', 'unknown')
                            plugin_description = plugin.get('description_for_model', '')
                            interface = plugin.get('interface', {})
                            paths = interface.get('paths', {})
                            
                            logger.info(f"⚙️ 處理插件: {plugin_name}，包含 {len(paths)} 個 API 端點")
                            
                            for path, methods in paths.items():
                                for method, spec in methods.items():
                                    if method.lower() in ['get', 'post', 'put', 'delete']:
                                        tool_name = spec.get('operationId', 
                                                            f"{method.lower()}_{plugin_name.replace('-', '_')}")
                                        
                                        input_schema = {"type": "object", "properties": {}}
                                        required_fields = []
                                        
                                        # 處理請求主體參數
                                        if 'requestBody' in spec:
                                            request_body = spec['requestBody']
                                            if 'content' in request_body:
                                                for content_type, content in request_body['content'].items():
                                                    if 'schema' in content:
                                                        body_schema = content['schema']
                                                        if 'properties' in body_schema:
                                                            input_schema['properties'].update(body_schema['properties'])
                                                        if 'required' in body_schema:
                                                            required_fields.extend(body_schema['required'])
                                        
                                        # 處理 URL 參數
                                        if 'parameters' in spec:
                                            for param in spec['parameters']:
                                                param_name = param['name']
                                                param_schema = param.get('schema', {"type": "string"})
                                                input_schema['properties'][param_name] = {
                                                    "type": param_schema.get('type', 'string'),
                                                    "description": param.get('description', '')
                                                }
                                                if param.get('required', False):
                                                    required_fields.append(param_name)
                                        
                                        if required_fields:
                                            input_schema['required'] = required_fields
                                        
                                        input_schema = flatten_enum(input_schema)
                                        
                                        tool = {
                                            "name": tool_name,
                                            "description": spec.get('summary', plugin_description),
                                            "inputSchema": input_schema,
                                            "_meta": {
                                                "base_url": SUPERIOR_API_BASE,
                                                "path": path,
                                                "method": method.upper(),
                                                "plugin_name": plugin_name,
                                                "original_spec": spec
                                            }
                                        }
                                        tools.append(tool)
                                        logger.info(f"✅ 創建工具: {tool_name}")
                    
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
    
    與 sse_server_v4_universal.py 保持一致的實現。
    
    Args:
        token (str): Superior APIs 認證 token
        tool_name (str): 要調用的工具名稱
        arguments (Dict): 工具調用參數
        
    Returns:
        Dict: 包含執行結果的字典
    """
    try:
        tools = tools_cache.get(token, [])
        tool_meta = None
        
        for tool in tools:
            if tool['name'] == tool_name:
                tool_meta = tool.get('_meta', {})
                break
        
        if not tool_meta:
            logger.error(f"❌ 工具 {tool_name} 未找到")
            return {
                "success": False,
                "error": f"工具 {tool_name} 不存在",
                "content": ""
            }
        
        base_url = tool_meta['base_url']
        path = tool_meta['path']
        method = tool_meta['method']
        full_url = f"{base_url}{path}"
        
        headers = {
            "token": token,
            "Content-Type": "application/json"
        }
        
        logger.info(f"🔨 調用 Superior API: {method} {full_url}，參數: {arguments}")
        
        async with aiohttp.ClientSession() as session:
            if method == 'GET':
                async with session.get(full_url, headers=headers, params=arguments) as response:
                    result = await response.text()
                    logger.info(f"📡 Superior API 回應 ({response.status}): {result[:200]}...")
                    return {
                        "success": response.status == 200,
                        "content": result,
                        "status_code": response.status
                    }
            else:
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


# === MCP Streamable HTTP 端點區段 ===

@app.post("/mcp")
@app.get("/mcp")
async def mcp_endpoint(request: Request, response: Response):
    """
    MCP Streamable HTTP 主要端點 - 符合官方規範
    
    處理 JSON-RPC 2.0 格式的 MCP 請求，支援以下方法：
    - initialize: 初始化 MCP 連線
    - tools/list: 獲取可用工具列表
    - tools/call: 調用特定工具
    
    支援單一請求和批次請求處理。
    """
    # 驗證請求來源
    if not validate_origin(request):
        return JSONResponse(
            status_code=403,
            content=create_jsonrpc_error(None, -32001, "Invalid origin")
        )
    
    # 提取會話 ID
    session_id = extract_session_id(request)
    if not session_id:
        session_id = generate_session_id()
        response.headers["Mcp-Session-Id"] = session_id
    
    # 處理 GET 請求（用於 SSE 或初始化）
    if request.method == "GET":
        return JSONResponse({
            "jsonrpc": "2.0",
            "result": {
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "instructions": "使用 POST 方法發送 JSON-RPC 2.0 請求",
                "server_info": {
                    "name": "Superior APIs MCP Server",
                    "version": "3.0.0"
                }
            }
        })
    
    # 處理 POST 請求
    try:
        body = await request.body()
        if not body:
            return JSONResponse(
                status_code=400,
                content=create_jsonrpc_error(None, -32700, "Parse error: Empty request body")
            )
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content=create_jsonrpc_error(None, -32700, f"Parse error: {str(e)}")
            )
        
        # 檢查是否為批次請求
        if isinstance(data, list):
            # 批次請求處理
            responses = []
            for item in data:
                try:
                    req = MCPRequest(**item)
                    result = await handle_mcp_request(req, request, session_id)
                    responses.append(result)
                except Exception as e:
                    responses.append(create_jsonrpc_error(
                        item.get("id"), -32600, f"Invalid Request: {str(e)}"
                    ))
            return JSONResponse(responses)
        
        else:
            # 單一請求處理
            try:
                req = MCPRequest(**data)
                result = await handle_mcp_request(req, request, session_id)
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content=create_jsonrpc_error(
                        data.get("id"), -32600, f"Invalid Request: {str(e)}"
                    )
                )
    
    except Exception as e:
        logger.error(f"❌ MCP endpoint 未知錯誤: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=create_jsonrpc_error(None, -32603, "Internal error")
        )


async def handle_mcp_request(request: MCPRequest, http_request: Request, session_id: str) -> Dict[str, Any]:
    """
    處理單一 MCP JSON-RPC 2.0 請求
    
    Args:
        request: MCP 請求物件
        http_request: FastAPI HTTP 請求物件
        session_id: 會話 ID
        
    Returns:
        Dict: JSON-RPC 2.0 回應
    """
    try:
        method = request.method
        params = request.params or {}
        request_id = request.id
        
        logger.info(f"🔍 處理 MCP 方法: {method}，會話: {session_id}")
        
        # 儲存會話資訊
        if session_id not in session_store:
            session_store[session_id] = {
                "created": datetime.now(),
                "last_access": datetime.now(),
                "initialized": False
            }
        session_store[session_id]["last_access"] = datetime.now()
        
        # 處理不同的 MCP 方法
        if method == "initialize":
            return await handle_initialize(request_id, params, session_id)
            
        elif method == "tools/list":
            return await handle_tools_list(request_id, params, http_request, session_id)
            
        elif method == "tools/call":
            return await handle_tools_call(request_id, params, http_request, session_id)
            
        else:
            return create_jsonrpc_error(
                request_id, -32601, f"Method not found: {method}"
            )
    
    except Exception as e:
        logger.error(f"❌ 處理 MCP 請求失敗: {str(e)}")
        return create_jsonrpc_error(
            request.id, -32603, f"Internal error: {str(e)}"
        )


async def handle_initialize(request_id: Any, params: Dict, session_id: str) -> Dict[str, Any]:
    """
    處理 MCP initialize 方法
    
    初始化 MCP 連線並返回伺服器能力。
    """
    try:
        # 標記會話為已初始化
        session_store[session_id]["initialized"] = True
        
        # 返回伺服器能力
        capabilities = {
            "tools": {},  # 支援工具功能
            "resources": {},  # 暫不支援資源
            "prompts": {}  # 暫不支援提示
        }
        
        server_info = {
            "name": "Superior APIs MCP Server",
            "version": "3.0.0"
        }
        
        result = {
            "capabilities": capabilities,
            "serverInfo": server_info,
            "protocolVersion": "2024-11-05"
        }
        
        logger.info(f"✅ MCP 連線已初始化，會話: {session_id}")
        return create_jsonrpc_response(request_id, result)
        
    except Exception as e:
        logger.error(f"❌ MCP 初始化失敗: {str(e)}")
        return create_jsonrpc_error(request_id, -32603, f"Initialize failed: {str(e)}")


async def handle_tools_list(request_id: Any, params: Dict, http_request: Request, session_id: str) -> Dict[str, Any]:
    """
    處理 MCP tools/list 方法
    
    返回所有可用的工具列表。
    """
    try:
        # 提取認證 token
        token = extract_token(http_request)
        if not token:
            return create_jsonrpc_error(
                request_id, -32002, "Authentication required: token missing"
            )
        
        if len(token) < 10:
            return create_jsonrpc_error(
                request_id, -32002, "Authentication failed: invalid token format"
            )
        
        # 獲取 Superior APIs 工具
        superior_tools = await fetch_superior_apis_tools(token)
        
        # 轉換為 MCP 格式
        mcp_tools = []
        for tool in superior_tools:
            mcp_tool = {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"]
            }
            mcp_tools.append(mcp_tool)
        
        result = {
            "tools": mcp_tools
        }
        
        logger.info(f"🔧 返回 {len(mcp_tools)} 個 MCP 工具，會話: {session_id}")
        return create_jsonrpc_response(request_id, result)
        
    except Exception as e:
        logger.error(f"❌ 獲取工具列表失敗: {str(e)}")
        return create_jsonrpc_error(request_id, -32603, f"Tools list failed: {str(e)}")


async def handle_tools_call(request_id: Any, params: Dict, http_request: Request, session_id: str) -> Dict[str, Any]:
    """
    處理 MCP tools/call 方法
    
    調用指定的工具並返回結果。
    """
    try:
        # 提取認證 token
        token = extract_token(http_request)
        if not token:
            return create_jsonrpc_error(
                request_id, -32002, "Authentication required: token missing"
            )
        
        # 驗證必要參數
        tool_name = params.get("name")
        if not tool_name:
            return create_jsonrpc_error(
                request_id, -32602, "Invalid params: 'name' is required"
            )
        
        arguments = params.get("arguments", {})
        
        logger.info(f"🔨 調用 MCP 工具: {tool_name}，會話: {session_id}")
        
        # 調用 Superior API 工具
        result = await call_superior_api_tool(token, tool_name, arguments)
        
        if result.get("success", False):
            mcp_result = {
                "content": [
                    {
                        "type": "text",
                        "text": result.get("content", "")
                    }
                ]
            }
            return create_jsonrpc_response(request_id, mcp_result)
        else:
            return create_jsonrpc_error(
                request_id, -32603, 
                f"Tool execution failed: {result.get('error', '未知錯誤')}"
            )
    
    except Exception as e:
        logger.error(f"❌ 調用工具失敗: {str(e)}")
        return create_jsonrpc_error(request_id, -32603, f"Tool call failed: {str(e)}")


# === REST API 端點區段（兼容性保留）===

@app.get("/")
async def root():
    """根路徑，提供 API 資訊和狀態"""
    total_cached_tools = sum(len(tools) for tools in tools_cache.values())
    
    return {
        "message": "Superior APIs MCP Streamable HTTP Server v3",
        "version": "3.0.0",
        "status": "running",
        "protocol": "MCP Streamable HTTP Transport",
        "compliance": "符合 MCP 官方規範 (2025-03-26)",
        "authentication": "header-token-based",
        "endpoints": {
            "mcp": "/mcp - MCP Streamable HTTP 主要端點 (支援 JSON-RPC 2.0)",
            "tools": "/tools - 取得所有可用工具清單 (需要 token) [兼容性端點]",
            "call": "/call - 調用指定工具 (需要 token) [兼容性端點]",
            "websocket": "/ws/{client_id} - WebSocket 連線端點 [兼容性端點]",
            "docs": "/docs - API 文件",
            "health": "/health - 健康檢查"
        },
        "statistics": {
            "cached_tokens": len(tools_cache),
            "total_cached_tools": total_cached_tools,
            "active_connections": len(active_connections)
        },
        "usage": {
            "mcp_endpoint": "POST /mcp with JSON-RPC 2.0 format",
            "token_header": "token: YOUR_SUPERIOR_APIS_TOKEN",
            "example_initialize": "POST /mcp: {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}",
            "example_tools": "POST /mcp: {\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\",\"params\":{}}",
            "compatibility": "curl -H 'token: your_token' http://localhost:8000/tools"
        }
    }

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server": "superior-apis-mcp-http-v3",
        "protocol": "MCP Streamable HTTP",
        "cache_status": {
            "cached_tokens": len(tools_cache),
            "total_tools": sum(len(tools) for tools in tools_cache.values())
        }
    }


@app.get("/tools", response_model=List[ToolInfo])
async def list_tools(request: Request):
    """
    取得所有可用工具的清單
    
    需要在 HTTP header 中提供有效的 token。
    
    Args:
        request: FastAPI 請求物件
        
    Returns:
        List[ToolInfo]: 工具資訊清單
        
    Raises:
        HTTPException: 當 token 缺失或無效時
    """
    # 提取並驗證 token
    token = extract_token(request)
    if not token:
        logger.warning("⚠️ 工具列表請求被拒絕: 未提供 token")
        raise HTTPException(status_code=401, detail="Token required in header")
    
    if len(token) < 10:
        logger.warning(f"⚠️ 工具列表請求被拒絕: Token 長度過短 ({len(token)} 字元)")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # 獲取工具列表
    superior_tools = await fetch_superior_apis_tools(token)
    
    tools = []
    for tool in superior_tools:
        tools.append(ToolInfo(
            name=tool['name'],
            description=tool['description'],
            schema=tool['inputSchema'],
            method=tool['_meta']['method'],
            path=tool['_meta']['path']
        ))
    
    logger.info(f"🔧 返回 {len(tools)} 個工具給客戶端")
    return tools


@app.post("/call", response_model=ToolCallResponse)
async def call_tool(tool_request: ToolCallRequest, request: Request):
    """
    調用指定的工具
    
    需要在 HTTP header 中提供有效的 token。
    
    Args:
        tool_request: 工具調用請求
        request: FastAPI 請求物件
        
    Returns:
        ToolCallResponse: 工具調用結果
        
    Raises:
        HTTPException: 當 token 缺失或工具不存在時
    """
    # 提取並驗證 token
    token = extract_token(request)
    if not token:
        logger.warning("⚠️ 工具調用被拒絕: 未提供 token")
        raise HTTPException(status_code=401, detail="Token required in header")
    
    if len(token) < 10:
        logger.warning(f"⚠️ 工具調用被拒絕: Token 長度過短 ({len(token)} 字元)")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # 獲取工具列表（如果尚未快取）
    superior_tools = await fetch_superior_apis_tools(token)
    if not superior_tools:
        logger.error(f"❌ 無法獲取 Superior APIs 工具列表，token: {token[:10]}...")
        raise HTTPException(status_code=500, detail="Unable to fetch tools from Superior APIs")
    
    logger.info(f"🔨 調用工具: {tool_request.name}")
    
    # 調用 Superior API 工具
    result = await call_superior_api_tool(token, tool_request.name, tool_request.arguments or {})
    
    if result.get("success", False):
        return ToolCallResponse(
            success=True,
            content=result.get("content", ""),
            timestamp=datetime.now().isoformat()
        )
    else:
        return ToolCallResponse(
            success=False,
            content=result.get("content", ""),
            error=result.get("error", "未知錯誤"),
            timestamp=datetime.now().isoformat()
        )


# === WebSocket 端點區段 ===

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket 連線端點
    
    提供即時雙向通訊功能。
    注意：這個端點不支援 token 認證，僅供示範使用。
    
    Args:
        websocket: WebSocket 連線物件
        client_id: 客戶端 ID
    """
    connection = await manager.connect(websocket, client_id)
    
    # 記錄連線資訊
    active_connections[client_id] = {
        'timestamp': datetime.now(),
        'client_type': 'websocket',
        'connection_id': connection.client_id
    }
    
    total_cached_tools = sum(len(tools) for tools in tools_cache.values())
    
    # 發送歡迎訊息
    await connection.send_message({
        "type": "connection",
        "message": "已成功連線到 Superior APIs MCP Streamable HTTP Server v3",
        "client_id": client_id,
        "note": "這個 WebSocket 連線不支援 token 認證，請使用 REST API",
        "cached_tools": total_cached_tools,
        "usage": "Use REST API endpoints with token header for full functionality"
    })
    
    try:
        while connection.connected:
            # 接收客戶端訊息
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "list_tools":
                # 處理列出工具的請求
                # 注意：由於 WebSocket 不支援 token 認證，這裡只能返回快取的工具
                token = message.get("token")
                if not token:
                    await connection.send_message({
                        "type": "error",
                        "message": "WebSocket 需要在訊息中提供 token 欄位"
                    })
                    continue
                
                superior_tools = await fetch_superior_apis_tools(token)
                
                tools = [
                    {
                        "name": tool['name'],
                        "description": tool['description'],
                        "schema": tool['inputSchema'],
                        "method": tool['_meta']['method'],
                        "path": tool['_meta']['path']
                    }
                    for tool in superior_tools
                ]
                
                await connection.send_message({
                    "type": "tools_list",
                    "tools": tools,
                    "total": len(tools)
                })
                
            elif message.get("type") == "call_tool":
                # 處理調用工具的請求
                tool_name = message.get("name")
                arguments = message.get("arguments", {})
                token = message.get("token")
                
                if not tool_name:
                    await connection.send_message({
                        "type": "error",
                        "message": "工具名稱不能為空"
                    })
                    continue
                
                if not token:
                    await connection.send_message({
                        "type": "error",
                        "message": "WebSocket 需要在訊息中提供 token 欄位"
                    })
                    continue
                
                # 調用 Superior API 工具
                result = await call_superior_api_tool(token, tool_name, arguments)
                
                await connection.send_message({
                    "type": "tool_response",
                    "tool_name": tool_name,
                    "success": result.get("success", False),
                    "content": result.get("content", ""),
                    "error": result.get("error"),
                    "timestamp": datetime.now().isoformat()
                })
            
            else:
                await connection.send_message({
                    "type": "error",
                    "message": f"未知的訊息類型: {message.get('type')}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(connection)
        active_connections.pop(client_id, None)
        logger.info(f"🔌 WebSocket 客戶端主動斷線: {client_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket 錯誤: {type(e).__name__}: {e}")
        manager.disconnect(connection)
        active_connections.pop(client_id, None)


# === 應用程式生命週期事件 ===

@app.on_event("startup")
async def startup_event():
    """應用程式啟動時的初始化"""
    logger.info("🚀 正在啟動 Superior APIs MCP Streamable HTTP Server v3...")
    logger.info("✅ 符合 MCP 官方規範 (2025-03-26)")
    logger.info("🔄 支援 JSON-RPC 2.0 和 Streamable HTTP 傳輸協定")
    logger.info("🎯 主要端點: POST /mcp (支援 initialize, tools/list, tools/call)")
    logger.info("🔒 認證方式: HTTP header token 提取")
    logger.info("🔗 兼容性: 保留舊版 REST API 端點")
    
    logger.info("✅ 伺服器啟動完成！")
    logger.info("📝 MCP 使用方式: POST /mcp 並發送 JSON-RPC 2.0 格式請求")
    logger.info("📝 兼容性使用: 在 HTTP header 中提供 'token: YOUR_SUPERIOR_APIS_TOKEN'")


@app.on_event("shutdown")
async def shutdown_event():
    """應用程式關閉時的清理"""
    logger.info("💯 正在關閉 Superior APIs MCP Streamable HTTP Server v3...")
    
    # 關閉所有 WebSocket 連線
    for connection in manager.active_connections:
        await connection.close()
    
    # 清理快取
    tools_cache.clear()
    active_connections.clear()
    
    logger.info("✅ 伺服器已成功關閉")


# === 伺服器啟動函數 ===

def main():
    """啟動 HTTP 伺服器的主要函數"""
    print("🚀 正在啟動 Superior APIs MCP Streamable HTTP Server v3...")
    print("✅ 符合 MCP 官方規範 (2025-03-26)")
    print("🔄 v3 版本新功能:")
    print("   - 實作 MCP Streamable HTTP 傳輸協定")
    print("   - 支援 JSON-RPC 2.0 訊息格式")
    print("   - 單一 /mcp 端點處理所有 MCP 方法")
    print("   - Mcp-Session-Id 會話管理")
    print("   - 保留舊版 REST API 作為兼容性端點")
    print("📍 伺服器將在以下地址提供服務:")
    print("   - http://localhost:8000")
    print("   - http://127.0.0.1:8000")
    print("🔑 認證方式: 在 HTTP header 中加入 'token: YOUR_SUPERIOR_APIS_TOKEN'")
    print("🎯 MCP 端點:")
    print("   - POST /mcp - MCP Streamable HTTP 主要端點 (JSON-RPC 2.0)")
    print("   - GET  /mcp - 獲取伺服器能力資訊")
    print("🔗 兼容性 API 端點:")
    print("   - GET  /tools - 獲取工具列表")
    print("   - POST /call  - 調用工具")
    print("   - GET  /health - 健康檢查")
    print("   - WS   /ws/{client_id} - WebSocket 連線")
    print("" + "="*60)
    
    # 使用 uvicorn 啟動 FastAPI 應用程式
    uvicorn.run(
        "mcp_superiorapis_remote.mcp_server_http:app",   # 模組名稱
        host=config.server_host,      # 監聽網路介面
        port=config.http_server_port,           # HTTP 伺服器端口
        reload=config.dev_mode,         # 開發模式自動重載
        log_level=config.log_level.lower()     # 日誌等級
    )


if __name__ == "__main__":
    main()