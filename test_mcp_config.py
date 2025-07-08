#!/usr/bin/env python3
"""
MCP SuperiorAPIs Server - 配置測試腳本

測試 HTTP 伺服器的配置和連接性。
支援從 .env 檔案或環境變數載入配置。

使用方式:
    python test_mcp_config.py
    python test_mcp_config.py --token YOUR_TOKEN
    python test_mcp_config.py --url http://localhost:8000/mcp
"""

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, Optional

import aiohttp
from src.mcp_superiorapis_remote.config import get_config


async def test_mcp_server(url: str, token: Optional[str] = None) -> bool:
    """
    測試 MCP 伺服器的基本功能
    
    Args:
        url: MCP 伺服器 URL
        token: Superior APIs token (可選)
        
    Returns:
        bool: 測試是否成功
    """
    print(f"🔍 Testing MCP server at: {url}")
    
    headers = {"Content-Type": "application/json"}
    if token:
        headers["token"] = token
        print(f"🔑 Using token: {token[:10]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 測試 1: GET 請求 (檢查伺服器是否運行)
            print("\n📡 Test 1: GET /mcp (server status)")
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Server is running")
                    print(f"   Protocol version: {data.get('result', {}).get('protocolVersion', 'unknown')}")
                else:
                    print(f"❌ GET request failed: {response.status}")
                    return False
            
            # 測試 2: MCP initialize
            print("\n📡 Test 2: MCP initialize")
            initialize_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {}
            }
            
            async with session.post(url, json=initialize_request, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if "result" in data:
                        print("✅ Initialize successful")
                        capabilities = data["result"].get("capabilities", {})
                        print(f"   Capabilities: {list(capabilities.keys())}")
                    else:
                        print(f"❌ Initialize failed: {data}")
                        return False
                else:
                    print(f"❌ Initialize request failed: {response.status}")
                    text = await response.text()
                    print(f"   Response: {text[:200]}...")
                    return False
            
            # 測試 3: Tools list (需要 token)
            if token:
                print("\n📡 Test 3: MCP tools/list")
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                
                async with session.post(url, json=tools_request, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "result" in data:
                            tools = data["result"].get("tools", [])
                            print(f"✅ Tools list successful: {len(tools)} tools available")
                            if tools:
                                print(f"   First tool: {tools[0].get('name', 'unnamed')}")
                        else:
                            print(f"❌ Tools list failed: {data}")
                            return False
                    else:
                        print(f"❌ Tools list request failed: {response.status}")
                        text = await response.text()
                        print(f"   Response: {text[:200]}...")
                        return False
            else:
                print("\n⏭️  Test 3: Skipped (no token provided)")
            
            print("\n✅ All tests passed!")
            return True
            
    except aiohttp.ClientError as e:
        print(f"❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="Test MCP SuperiorAPIs Server configuration and connectivity"
    )
    
    parser.add_argument(
        "--url",
        help="MCP server URL (default: from config)"
    )
    
    parser.add_argument(
        "--token",
        help="Superior APIs token (required for tools/list test)"
    )
    
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show current configuration"
    )
    
    args = parser.parse_args()
    
    # 載入配置
    config = get_config()
    
    if args.config:
        print("🔧 Current Configuration:")
        config.print_config()
        
        # 驗證配置
        errors = config.validate()
        if errors:
            print("\n❌ Configuration errors:")
            for error in errors:
                print(f"   {error}")
            sys.exit(1)
        else:
            print("\n✅ Configuration is valid")
        return
    
    # 取得測試參數
    url = args.url or config.test_mcp_server_url
    token = args.token  # Token 現在只能通過命令列參數提供
    
    print("🚀 MCP SuperiorAPIs Server - Configuration Test")
    print("=" * 50)
    print(f"Server URL: {url}")
    print(f"Token: {'✅ Provided' if token else '❌ Missing'}")
    print("=" * 50)
    
    # 執行非同步測試
    success = asyncio.run(test_mcp_server(url, token))
    
    if not success:
        print("\n❌ Tests failed. Please check:")
        print("   1. Is the MCP server running?")
        print("   2. Is the URL correct?")
        print("   3. Is the token valid? (use --token to provide one)")
        print(f"   4. Check your .env file for server configuration")
        sys.exit(1)
    
    print("\n🎉 All tests completed successfully!")


if __name__ == "__main__":
    main()