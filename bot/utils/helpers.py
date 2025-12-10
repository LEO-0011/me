"""
Helper utilities
"""

import re
import unicodedata
from pathlib import Path


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem usage"""
    # Normalize unicode characters
    filename = unicodedata.normalize('NFKD', filename)
    
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    filename = ''.join(c for c in filename if ord(c) >= 32)
    
    # Limit length
    name = Path(filename).stem[:200]
    ext = Path(filename).suffix[:20]
    
    return f"{name}{ext}" if ext else name


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return Path(filename).suffix.lower()


def is_valid_mega_link(link: str) -> bool:
    """Validate MEGA folder link format"""
    patterns = [
        r'https?://mega\.nz/folder/[a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+',
        r'https?://mega\.nz/#F![a-zA-Z0-9_-]+![a-zA-Z0-9_-]+',
        r'https?://mega\.co\.nz/folder/[a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+',
        r'https?://mega\.co\.nz/#F![a-zA-Z0-9_-]+![a-zA-Z0-9_-]+',
    ]
    
    return any(re.match(pattern, link) for pattern in patterns)


def parse_mega_folder_id(link: str) -> tuple[str, str]:
    """Extract folder ID and key from MEGA link"""
    # New format: mega.nz/folder/ID#KEY
    match = re.search(r'mega\.(?:nz|co\.nz)/folder/([a-zA-Z0-9_-]+)#([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1), match.group(2)
    
    # Old format: mega.nz/#F!ID!KEY
    match = re.search(r'mega\.(?:nz|co\.nz)/#F!([a-zA-Z0-9_-]+)!([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1), match.group(2)
    
    raise ValueError("Invalid MEGA folder link format")
