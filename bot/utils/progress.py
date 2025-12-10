"""
Progress tracking utilities for downloads and uploads
"""

import asyncio
import time
from typing import Optional, Callable
from dataclasses import dataclass, field


@dataclass
class ProgressData:
    """Data class for progress information"""
    current: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int = 0
    percentage: float = 0.0
    filename: str = ""
    status: str = "pending"
    start_time: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)


class ProgressTracker:
    """Track download/upload progress with rate limiting"""
    
    def __init__(self, update_interval: float = 2.0):
        self.update_interval = update_interval
        self.progress_data: dict[int, ProgressData] = {}
        self._callbacks: dict[int, Callable] = {}
        self._locks: dict[int, asyncio.Lock] = {}
    
    def create_session(self, user_id: int, filename: str, total_size: int) -> ProgressData:
        """Create a new progress tracking session"""
        self.progress_data[user_id] = ProgressData(
            total=total_size,
            filename=filename,
            status="downloading"
        )
        self._locks[user_id] = asyncio.Lock()
        return self.progress_data[user_id]
    
    def get_progress(self, user_id: int) -> Optional[ProgressData]:
        """Get current progress for user"""
        return self.progress_data.get(user_id)
    
    async def update(self, user_id: int, current: int) -> bool:
        """
        Update progress and return True if callback should be triggered
        Rate-limited to prevent Telegram API flooding
        """
        if user_id not in self.progress_data:
            return False
        
        async with self._locks[user_id]:
            data = self.progress_data[user_id]
            now = time.time()
            
            # Update current progress
            data.current = current
            
            # Calculate percentage
            if data.total > 0:
                data.percentage = (current / data.total) * 100
            
            # Calculate speed and ETA
            elapsed = now - data.start_time
            if elapsed > 0:
                data.speed = current / elapsed
                if data.speed > 0:
                    remaining = data.total - current
                    data.eta = int(remaining / data.speed)
            
            # Check if we should trigger callback (rate limiting)
            if now - data.last_update >= self.update_interval:
                data.last_update = now
                return True
            
            return False
    
    def set_status(self, user_id: int, status: str):
        """Set status for user progress"""
        if user_id in self.progress_data:
            self.progress_data[user_id].status = status
    
    def complete(self, user_id: int):
        """Mark progress as complete"""
        if user_id in self.progress_data:
            data = self.progress_data[user_id]
            data.current = data.total
            data.percentage = 100.0
            data.status = "complete"
    
    def clear(self, user_id: int):
        """Clear progress data for user"""
        self.progress_data.pop(user_id, None)
        self._locks.pop(user_id, None)
        self._callbacks.pop(user_id, None)
    
    def format_progress_bar(self, user_id: int, width: int = 20) -> str:
        """Generate a text progress bar"""
        data = self.progress_data.get(user_id)
        if not data:
            return "No active transfer"
        
        filled = int(width * data.percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        
        return (
            f"📁 {data.filename}\n"
            f"[{bar}] {data.percentage:.1f}%\n"
            f"📊 {format_size(data.current)} / {format_size(data.total)}\n"
            f"⚡ {format_size(data.speed)}/s\n"
            f"⏱️ ETA: {format_time(data.eta)}\n"
            f"📌 Status: {data.status}"
        )


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def format_time(seconds: int) -> str:
    """Format seconds to human readable time"""
    if seconds < 0:
        return "Unknown"
    
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(secs)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(secs)}s"
    else:
        return f"{int(secs)}s"
