#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate server functionality without external requests
"""

import sys
import os
import asyncio
import aiohttp
sys.path.insert(0, '.')

# 測試函數
async def test_endpoints():
    """Test all endpoints using aiohttp"""
    print("=== Dify MCP Standalone Server Validation ===")
    
    # 測試配置
    base_url = "http://127.0.0.1:9000"
    
    async with aiohttp.ClientSession() as session:
        # 1. 測試健康檢查
        print("1. Testing health endpoint...")
        try:
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   OK Health: {data}")
                else:
                    print(f"   FAIL Health: {response.status}")
        except Exception as e:
            print(f"   ERROR Health: {e}")
        
        # 2. 測試工具端點
        print("2. Testing tools endpoint...")
        try:
            async with session.get(f"{base_url}/tools") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   OK Tools: {data.get('total', 0)} tools")
                else:
                    print(f"   FAIL Tools: {response.status}")
        except Exception as e:
            print(f"   ERROR Tools: {e}")
        
        # 3. 測試 MCP initialize
        print("3. Testing MCP initialize...")
        try:
            mcp_data = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {}
            }
            async with session.post(f"{base_url}/mcp", json=mcp_data) as response:
                if response.status == 200:
                    data = await response.json()
                    if "result" in data:
                        server_name = data["result"]["serverInfo"]["name"]
                        print(f"   OK Initialize: {server_name}")
                    else:
                        print(f"   FAIL Initialize: No result")
                else:
                    print(f"   FAIL Initialize: {response.status}")
        except Exception as e:
            print(f"   ERROR Initialize: {e}")
        
        # 4. 測試 MCP tools/list
        print("4. Testing MCP tools/list...")
        try:
            mcp_data = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            async with session.post(f"{base_url}/mcp", json=mcp_data) as response:
                if response.status == 200:
                    data = await response.json()
                    if "result" in data and "tools" in data["result"]:
                        tools_count = len(data["result"]["tools"])
                        print(f"   OK Tools list: {tools_count} tools")
                        
                        # 顯示前幾個工具
                        if tools_count > 0:
                            print("   Sample tools:")
                            for i, tool in enumerate(data["result"]["tools"][:3]):
                                print(f"      {i+1}. {tool['name']}: {tool['description'][:50]}...")
                    else:
                        print(f"   FAIL Tools list: No tools in result")
                else:
                    print(f"   FAIL Tools list: {response.status}")
        except Exception as e:
            print(f"   ERROR Tools list: {e}")

# 直接測試函數（不需要服務器運行）
def test_functions():
    """Test internal functions directly"""
    print("\n=== Direct Function Testing ===")
    
    try:
        from dify_mcp_standalone import extract_token, fetch_superior_tools, DEFAULT_TOKEN
        
        # 創建模擬請求對象
        class MockRequest:
            def __init__(self):
                self.headers = {"token": DEFAULT_TOKEN}
                self.query_params = {}
        
        mock_request = MockRequest()
        
        # 測試 token 提取
        print("1. Testing token extraction...")
        token = extract_token(mock_request)
        if token:
            print(f"   OK Token extracted: {token[:20]}...")
        else:
            print("   FAIL Token extraction failed")
        
        # 測試工具獲取（異步）
        print("2. Testing tool fetching...")
        async def test_fetch():
            tools = await fetch_superior_tools(DEFAULT_TOKEN)
            if tools:
                print(f"   OK Tools fetched: {len(tools)} tools")
                if len(tools) > 0:
                    print(f"   First tool: {tools[0]['name']}")
            else:
                print("   FAIL No tools fetched")
        
        asyncio.run(test_fetch())
        
    except Exception as e:
        print(f"   ERROR Function test: {e}")

if __name__ == "__main__":
    print("Starting server validation...")
    print("WARNING: Make sure the server is running in another terminal!")
    print()
    
    # 直接函數測試
    test_functions()
    
    # 網路端點測試
    print("\n" + "="*50)
    print("Press Enter to test network endpoints (server must be running)...")
    input()
    
    asyncio.run(test_endpoints())
    
    print("\nValidation complete!")