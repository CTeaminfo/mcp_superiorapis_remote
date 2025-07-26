#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dify MCP 專用服務器

完全獨立的、專門為 Dify MCP SSE 插件設計的服務器
與原有架構完全分離，使用不同端口和獨立功能
"""

import asyncio
import json
import logging
import aiohttp
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# === 配置 ===
DIFY_MCP_PORT = 9000  # 使用全新端口，避免衝突
SUPERIOR_API_BASE = "https://superiorapis-creator.cteam.com.tw"
PLUGINS_LIST_URL = f"{SUPERIOR_API_BASE}/manager/module/plugins/list_v3"
DEFAULT_TOKEN = None  # 不使用預設 token，必須由客戶端提供

# 快取設定
CACHE_TTL = 5 * 60  # 5分鐘快取過期時間（考慮到Dify也會快取）

# === 日誌設置 ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === FastAPI 應用 ===
app = FastAPI(title="Dify MCP Standalone Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 全域變數 ===
tools_cache = {}  # 清空快取

def extract_token(request: Request) -> str:
    """提取認證 token，優先使用config中的token"""
    # 檢查 headers（來自 MCP config）
    token = request.headers.get("token")
    if token:
        logger.info("🔧 使用 MCP config 中的 token")
        return token
    
    # 檢查 Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        logger.info("🔧 使用 Authorization Bearer token")
        return auth_header[7:]
    
    # 檢查 URL 參數
    token = request.query_params.get("token")
    if token:
        logger.info("🔧 使用 URL 參數中的 token")
        return token
    
    # 如果都沒有，返回錯誤
    logger.error("❌ 未找到 token，請在 MCP 配置中提供")
    raise HTTPException(status_code=401, detail="Token required. Please provide token in headers.")

async def fetch_superior_tools(token: str) -> List[Dict[str, Any]]:
    """獲取 Superior APIs 工具列表"""
    # 檢查快取
    current_time = time.time()
    if token in tools_cache:
        cache_data = tools_cache[token]
        if current_time - cache_data["timestamp"] < CACHE_TTL:
            logger.info(f"🔄 使用快取的工具列表 (剩餘 {int((CACHE_TTL - (current_time - cache_data['timestamp'])) / 60)} 分鐘)")
            return cache_data["tools"]
        else:
            logger.info("⏰ 快取已過期，重新獲取工具")
            del tools_cache[token]
    
    try:
        headers = {
            "token": token,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            logger.info("🌐 獲取 Superior APIs 工具列表...")
            async with session.post(PLUGINS_LIST_URL, headers=headers, json={}) as response:
                if response.status != 200:
                    logger.error(f"❌ Superior APIs 請求失敗: {response.status}")
                    return []
                
                data = await response.json()
                tools = []
                
                if 'plugins' not in data:
                    logger.warning("⚠️ 未找到插件資料")
                    return []
                
                logger.info(f"📦 處理 {len(data['plugins'])} 個插件")
                
                for plugin_item in data['plugins']:
                    try:
                        plugin = plugin_item.get('plugin', {})
                        plugin_name = plugin.get('name_for_model', 'unknown')
                        plugin_desc = plugin.get('description_for_model', '')
                        
                        logger.info(f"🔍 處理插件: {plugin_name}")
                        
                        # 路徑在 plugin.interface 中
                        interface = plugin.get('interface', {})
                        paths = interface.get('paths', {})
                        logger.info(f"📊 插件 {plugin_name} 有 {len(paths)} 個路徑")
                        
                        for path, methods in paths.items():
                            for method, spec in methods.items():
                                if method.lower() in ['get', 'post', 'put', 'delete']:
                                    tool_name = spec.get('operationId', f"{method}_{plugin_name}")
                                    logger.info(f"✅ 處理工具: {tool_name} ({method.upper()})")
                                    
                                    # 使用 OpenAPI 原始格式（保持規格完整性）
                                    
                                    if method.lower() in ['post', 'put', 'patch']:
                                        # POST/PUT/PATCH：使用 requestBody
                                        if 'requestBody' in spec:
                                            parameters = {
                                                "summary": spec.get('summary', plugin_desc),
                                                "requestBody": spec['requestBody']
                                            }
                                        else:
                                            parameters = {
                                                "summary": spec.get('summary', plugin_desc)
                                            }
                                    
                                    elif method.lower() in ['get', 'delete']:
                                        # GET/DELETE：使用 parameters 數組
                                        if 'parameters' in spec:
                                            params_list = spec['parameters']
                                            parameters = {
                                                "summary": spec.get('summary', plugin_desc),
                                                "parameters": params_list if params_list is not None else []
                                            }
                                        else:
                                            parameters = {
                                                "summary": spec.get('summary', plugin_desc),
                                                "parameters": []
                                            }
                                    
                                    # 保存原始 OpenAPI 定義用於調用時參數分配
                                    api_info = {
                                        "url": f"{SUPERIOR_API_BASE}{path}",
                                        "method": method.upper(),
                                        "plugin": plugin_name,
                                        "original_spec": spec  # 保存完整的 OpenAPI spec
                                    }
                                    
                                    # 創建工具
                                    tool = {
                                        "name": tool_name,
                                        "description": spec.get('summary', plugin_desc),
                                        "parameters": parameters,
                                        "_api_info": api_info
                                    }
                                    tools.append(tool)
                                    logger.info(f"✅ 成功創建工具: {tool_name} ({method.upper()})")
                    except Exception as e:
                        logger.error(f"❌ 處理插件 {plugin_name} 時發生錯誤: {e}")
                        continue
                
                # 儲存到快取
                tools_cache[token] = {
                    "tools": tools,
                    "timestamp": time.time()
                }
                logger.info(f"✅ 成功獲取 {len(tools)} 個工具並儲存到快取")
                return tools
                
    except Exception as e:
        logger.error(f"❌ 獲取工具失敗: {e}")
        return []

async def call_superior_tool(token: str, tool_name: str, arguments: Dict) -> Dict:
    """調用 Superior APIs 工具"""
    # 取得工具列表（可能來自快取或重新獲取）
    tools = await fetch_superior_tools(token)
    
    # 找到對應工具
    target_tool = None
    for tool in tools:
        if tool['name'] == tool_name:
            target_tool = tool
            break
    
    if not target_tool:
        return {"error": f"Tool '{tool_name}' not found"}
    
    api_info = target_tool['_api_info']
    url = api_info['url']
    method = api_info['method']
    original_spec = api_info.get('original_spec', {})
    
    try:
        # 分離參數類型
        query_params = {}
        path_params = {}
        header_params = {}
        body_params = {}
        
        logger.info(f"🔍 分配參數 for {tool_name} ({method})")
        
        # 處理 GET/DELETE 方法的 parameters 數組
        if method in ['GET', 'DELETE'] and 'parameters' in original_spec:
            params_list = original_spec.get('parameters', [])
            if params_list:
                for param_def in params_list:
                    if isinstance(param_def, dict):
                        param_name = param_def.get('name')
                        param_in = param_def.get('in', 'query')  # 默認為 query
                        
                        if param_name in arguments:
                            value = arguments[param_name]
                            if param_in == 'query':
                                query_params[param_name] = value
                            elif param_in == 'path':
                                path_params[param_name] = value
                            elif param_in == 'header':
                                header_params[param_name] = value
        
        # 處理 POST/PUT 方法的 requestBody
        elif method in ['POST', 'PUT', 'PATCH']:
            # 所有參數都放到 body 中
            body_params = arguments.copy()
        
        # 設置 headers
        headers = {
            "token": token,
            "Content-Type": "application/json"
        }
        headers.update(header_params)  # 添加自定義 headers
        
        # 處理 path 參數（替換 URL 中的佔位符）
        final_url = url
        for param_name, value in path_params.items():
            final_url = final_url.replace(f"{{{param_name}}}", str(value))
        
        async with aiohttp.ClientSession() as session:
            logger.info(f"🚀 調用工具: {tool_name} ({method}) -> {final_url}")
            
            if method == 'GET':
                async with session.get(final_url, headers=headers, params=query_params) as response:
                    result = await response.text()
            else:
                async with session.request(method, final_url, headers=headers, json=body_params) as response:
                    result = await response.text()
            
            # 嘗試解析為 JSON
            try:
                json_result = json.loads(result)
                return json_result
            except json.JSONDecodeError:
                return {"result": result}
                
    except Exception as e:
        logger.error(f"❌ 工具調用失敗: {e}")
        return {"error": str(e)}

# === MCP 端點 ===

@app.post("/mcp")
@app.get("/mcp")
async def mcp_endpoint(request: Request):
    """Dify MCP 專用端點"""
    try:
        if request.method == "POST":
            body = await request.json()
        else:
            # GET 請求，默認處理 tools/list
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
        
        method = body.get("method", "")
        request_id = body.get("id", 1)
        params = body.get("params", {})
        
        logger.info(f"📨 收到 MCP 請求: {method}")
        
        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {
                        "name": "Dify MCP Standalone Server",
                        "version": "1.0.0"
                    },
                    "protocolVersion": "2024-11-05"
                }
            })
        
        elif method == "tools/list":
            token = extract_token(request)
            tools = await fetch_superior_tools(token)
            
            logger.info(f"🔄 轉換 {len(tools)} 個工具為 MCP 格式")
            
            # 轉換為 MCP 格式
            mcp_tools = []
            for tool in tools:
                mcp_tool = {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["parameters"]  # MCP 使用 inputSchema 而不是 parameters
                }
                mcp_tools.append(mcp_tool)
            
            logger.info(f"🎯 返回 {len(mcp_tools)} 個 MCP 工具")
            
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": mcp_tools
                }
            })
        
        elif method == "tools/call":
            token = extract_token(request)
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if not tool_name:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "Missing tool name"}
                })
            
            result = await call_superior_tool(token, tool_name, arguments)
            
            # Dify 格式回應
            content = [{
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2)
            }]
            
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": content
                }
            })
        
        elif method == "notifications/initialized":
            # 通知方法不需要返回結果，只記錄日誌
            logger.info("✅ 收到初始化完成通知")
            return JSONResponse({})
        
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            })
            
    except Exception as e:
        logger.error(f"❌ MCP 端點錯誤: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32603, "message": str(e)}
        })

@app.get("/health")
async def health():
    """健康檢查"""
    return {"status": "ok", "server": "Dify MCP Standalone", "port": DIFY_MCP_PORT}

@app.get("/tools")
async def get_tools(request: Request):
    """快速查看可用工具"""
    token = extract_token(request)
    tools = await fetch_superior_tools(token)
    return {
        "total": len(tools),
        "token_source": "config" if request.headers.get("token") else "default",
        "tools": [{"name": t["name"], "description": t["description"]} for t in tools]
    }

@app.post("/clear-cache")
async def clear_cache(request: Request):
    """清除工具快取"""
    global tools_cache
    
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    token = body.get("token")
    
    if token:
        # 清除特定 token 的快取
        if token in tools_cache:
            del tools_cache[token]
            logger.info(f"🗑️ 已清除 token {token[:10]}... 的快取")
            return {"status": "ok", "message": f"Cache cleared for token"}
        else:
            return {"status": "ok", "message": "No cache found for token"}
    else:
        # 清除所有快取
        tools_cache.clear()
        logger.info("🗑️ 已清除所有工具快取")
        return {"status": "ok", "message": "All cache cleared"}

@app.get("/cache-status")
async def cache_status():
    """查看快取狀態"""
    status = {}
    current_time = time.time()
    
    for token, cache_data in tools_cache.items():
        remaining = CACHE_TTL - (current_time - cache_data["timestamp"])
        status[token[:10] + "..."] = {
            "tools_count": len(cache_data["tools"]),
            "remaining_minutes": max(0, int(remaining / 60)),
            "expired": remaining <= 0
        }
    
    return {
        "cache_ttl_minutes": CACHE_TTL // 60,
        "cached_tokens": len(tools_cache),
        "status": status
    }

# === 主程式 ===
def main():
    """啟動服務器"""
    print("🚀 啟動 Dify MCP Standalone Server")
    print(f"📡 埠號: {DIFY_MCP_PORT}")
    print(f"🔗 MCP 端點: http://localhost:{DIFY_MCP_PORT}/mcp")
    print(f"❤️ 健康檢查: http://localhost:{DIFY_MCP_PORT}/health")
    print(f"🛠️ 工具列表: http://localhost:{DIFY_MCP_PORT}/tools")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # 允許外部訪問
        port=DIFY_MCP_PORT,
        log_level="info",
        access_log=True  # 顯示訪問日誌
    )

if __name__ == "__main__":
    main()