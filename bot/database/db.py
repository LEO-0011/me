"""
SQLite database for session persistence and resume support
"""

import json
import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from bot.utils.config import Config


class Database:
    """Async SQLite database manager"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def _ensure_connected(self):
        """Ensure database connection is established"""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._create_tables()
    
    async def _create_tables(self):
        """Create database tables if they don't exist"""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_link TEXT NOT NULL,
                current_index INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, status)
            );
            
            CREATE TABLE IF NOT EXISTS session_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                file_index INTEGER NOT NULL,
                file_handle TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_files_session ON session_files(session_id);
        """)
        await self._conn.commit()
    
    async def create_session(
        self, 
        user_id: int, 
        folder_link: str, 
        files: List[Dict[str, Any]]
    ) -> int:
        """Create a new download session"""
        await self._ensure_connected()
        
        # Cancel any existing active sessions for this user
        await self._conn.execute("""
            UPDATE sessions 
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND status IN ('pending', 'downloading')
        """, (user_id,))
        
        # Create new session
        cursor = await self._conn.execute("""
            INSERT INTO sessions (user_id, folder_link, status)
            VALUES (?, ?, 'downloading')
        """, (user_id, folder_link))
        
        session_id = cursor.lastrowid
        
        # Insert files
        for idx, file_info in enumerate(files):
            await self._conn.execute("""
                INSERT INTO session_files 
                (session_id, file_index, file_handle, file_name, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                idx,
                file_info.get('handle', file_info.get('h', '')),
                file_info['name'],
                file_info['size']
            ))
        
        await self._conn.commit()
        return session_id
    
    async def get_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get active session for user"""
        await self._ensure_connected()
        
        cursor = await self._conn.execute("""
            SELECT id, user_id, folder_link, current_index, status, created_at, updated_at
            FROM sessions
            WHERE user_id = ? AND status IN ('pending', 'downloading')
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        
        row = await cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    async def get_session_files(self, session_id: int) -> List[Dict[str, Any]]:
        """Get files for a session"""
        await self._ensure_connected()
        
        cursor = await self._conn.execute("""
            SELECT file_index, file_handle as handle, file_name as name, file_size as size, status
            FROM session_files
            WHERE session_id = ?
            ORDER BY file_index
        """, (session_id,))
        
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def update_session_index(self, session_id: int, new_index: int):
        """Update current file index for session"""
        await self._ensure_connected()
        
        await self._conn.execute("""
            UPDATE sessions
            SET current_index = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_index, session_id))
        
        # Mark completed files
        await self._conn.execute("""
            UPDATE session_files
            SET status = 'completed'
            WHERE session_id = ? AND file_index < ?
        """, (session_id, new_index))
        
        await self._conn.commit()
    
    async def complete_session(self, session_id: int):
        """Mark session as completed"""
        await self._ensure_connected()
        
        await self._conn.execute("""
            UPDATE sessions
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))
        
        await self._conn.execute("""
            UPDATE session_files
            SET status = 'completed'
            WHERE session_id = ?
        """, (session_id,))
        
        await self._conn.commit()
    
    async def cancel_session(self, session_id: int):
        """Cancel a session"""
        await self._ensure_connected()
        
        await self._conn.execute("""
            UPDATE sessions
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))
        
        await self._conn.commit()
    
    async def get_all_pending_sessions(self) -> List[Dict[str, Any]]:
        """Get all pending/interrupted sessions for resume on startup"""
        await self._ensure_connected()
        
        cursor = await self._conn.execute("""
            SELECT id, user_id, folder_link, current_index, status
            FROM sessions
            WHERE status = 'downloading'
            ORDER BY updated_at DESC
        """)
        
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def cleanup_old_sessions(self, days: int = 7):
        """Clean up old completed/cancelled sessions"""
        await self._ensure_connected()
        
        await self._conn.execute("""
            DELETE FROM sessions
            WHERE status IN ('completed', 'cancelled')
            AND updated_at < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        await self._conn.commit()
    
    async def close(self):
        """Close database connection"""
        if self._conn:
            await self._conn.close()
            self._conn = None
