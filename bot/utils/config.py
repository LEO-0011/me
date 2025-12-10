"""
Configuration management using environment variables
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from environment variables"""
    
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # MEGA credentials
    MEGA_EMAIL: str = os.getenv("MEGA_EMAIL", "")
    MEGA_PASSWORD: str = os.getenv("MEGA_PASSWORD", "")
    
    # Storage
    STORAGE_PATH: Path = Path(os.getenv("STORAGE_PATH", "/downloads"))
    
    # Limits
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 2147483648))  # 2GB
    
    # Retry settings
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", 5))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", 60))
    
    # Database
    DB_PATH: Path = Path(os.getenv("DB_PATH", "data/bot.db"))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        
        # Create storage directory if not exists
        cls.STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        return True
    
    @classmethod
    def has_mega_credentials(cls) -> bool:
        """Check if MEGA credentials are provided"""
        return bool(cls.MEGA_EMAIL and cls.MEGA_PASSWORD)
