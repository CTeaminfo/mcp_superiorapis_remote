"""
MCP SuperiorAPIs 配置管理模組

這個模組負責從環境變數和 .env 檔案載入配置設定，
提供統一的配置介面給所有伺服器使用。
"""

import os
import logging
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# 取得專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent.parent

class Config:
    """配置管理類別"""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        初始化配置
        
        Args:
            env_file: 指定 .env 檔案路徑，預設為專案根目錄的 .env
        """
        self._load_env_file(env_file)
        self._setup_logging()
    
    def _load_env_file(self, env_file: Optional[str] = None):
        """載入 .env 檔案"""
        if not DOTENV_AVAILABLE:
            logging.warning("python-dotenv 未安裝，將只使用系統環境變數")
            return
        
        if env_file is None:
            env_file = PROJECT_ROOT / ".env"
        
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logging.info(f"已載入環境變數檔案: {env_path}")
        else:
            logging.info(f"未找到 .env 檔案: {env_path}，使用系統環境變數")
    
    def _setup_logging(self):
        """設置日誌級別"""
        log_level = self.log_level
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))
    
    # === Superior APIs 配置 ===
    
    @property
    def superior_api_base(self) -> str:
        """Superior APIs 基礎 URL"""
        return os.getenv("SUPERIOR_API_BASE", "https://superiorapis-creator.cteam.com.tw")
    
    @property
    def plugins_list_endpoint(self) -> str:
        """插件列表端點路徑"""
        return os.getenv("PLUGINS_LIST_ENDPOINT", "/manager/module/plugins/list_v3")
    
    @property
    def plugins_list_url(self) -> str:
        """完整的插件列表 URL"""
        return f"{self.superior_api_base}{self.plugins_list_endpoint}"
    
    # === 伺服器配置 ===
    
    @property
    def http_server_port(self) -> int:
        """HTTP 伺服器端口"""
        return int(os.getenv("HTTP_SERVER_PORT", "8000"))
    
    @property
    def sse_server_port(self) -> int:
        """SSE 伺服器端口"""
        return int(os.getenv("SSE_SERVER_PORT", "8080"))
    
    @property
    def server_host(self) -> str:
        """伺服器主機地址"""
        return os.getenv("SERVER_HOST", "0.0.0.0")
    
    # === 開發和除錯配置 ===
    
    @property
    def log_level(self) -> str:
        """日誌級別"""
        return os.getenv("LOG_LEVEL", "INFO")
    
    @property
    def dev_mode(self) -> bool:
        """開發模式"""
        return os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes", "on")
    
    @property
    def allowed_origins(self) -> List[str]:
        """允許的來源列表 (CORS)"""
        origins = os.getenv("ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1")
        return [origin.strip() for origin in origins.split(",") if origin.strip()]
    
    # === 快取配置 ===
    
    @property
    def cache_expiry(self) -> int:
        """快取過期時間（秒）"""
        return int(os.getenv("CACHE_EXPIRY", "3600"))
    
    # === 測試配置 ===
    
    @property
    def test_mcp_server_url(self) -> str:
        """測試用 MCP 伺服器 URL"""
        return os.getenv("TEST_MCP_SERVER_URL", f"http://localhost:{self.http_server_port}/mcp")
    
    @property
    def test_sse_server_url(self) -> str:
        """測試用 SSE 伺服器 URL"""
        return os.getenv("TEST_SSE_SERVER_URL", f"http://localhost:{self.sse_server_port}")
    
    # === 安全配置 ===
    
    @property
    def validate_origin(self) -> bool:
        """是否啟用 Origin 驗證"""
        return os.getenv("VALIDATE_ORIGIN", "true").lower() in ("true", "1", "yes", "on")
    
    @property
    def session_timeout(self) -> int:
        """Session 過期時間（秒）"""
        return int(os.getenv("SESSION_TIMEOUT", "7200"))
    
    # === 配置驗證 ===
    
    def validate(self) -> List[str]:
        """
        驗證配置是否正確
        
        Returns:
            錯誤訊息列表，空列表表示配置正確
        """
        errors = []
        
        # 注意: TOKEN 認證由客戶端在請求中提供，伺服器不需要配置 TOKEN
        
        if not self.superior_api_base.startswith("http"):
            errors.append("❌ SUPERIOR_API_BASE 必須以 http:// 或 https:// 開頭")
        
        if not (1 <= self.http_server_port <= 65535):
            errors.append("❌ HTTP_SERVER_PORT 必須在 1-65535 範圍內")
        
        if not (1 <= self.sse_server_port <= 65535):
            errors.append("❌ SSE_SERVER_PORT 必須在 1-65535 範圍內")
        
        if self.log_level.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append("❌ LOG_LEVEL 必須為 DEBUG, INFO, WARNING, ERROR, CRITICAL 其中之一")
        
        return errors
    
    def print_config(self):
        """印出當前配置"""
        print("🔧 MCP SuperiorAPIs 伺服器配置:")
        print(f"   Superior API: {self.superior_api_base}")
        print(f"   HTTP 端口: {self.http_server_port}")
        print(f"   SSE 端口: {self.sse_server_port}")
        print(f"   主機: {self.server_host}")
        print(f"   日誌級別: {self.log_level}")
        print(f"   開發模式: {self.dev_mode}")
        print(f"   Origin 驗證: {self.validate_origin}")
        print(f"   快取過期: {self.cache_expiry} 秒")
        print("ℹ️  Token 認證由客戶端在請求中提供")

# 建立全域配置實例
config = Config()

# 匯出常用函數
def get_config() -> Config:
    """取得配置實例"""
    return config

def reload_config(env_file: Optional[str] = None) -> Config:
    """重新載入配置"""
    global config
    config = Config(env_file)
    return config