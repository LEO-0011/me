"""
MEGA.nz downloader with progress support
"""

import asyncio
import os
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from mega import Mega
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from bot.utils.config import Config


class MegaQuotaError(Exception):
    """MEGA bandwidth quota exceeded"""
    pass


class MegaDownloadError(Exception):
    """General MEGA download error"""
    pass


class MegaDownloader:
    """Async wrapper for MEGA operations"""
    
    def __init__(self):
        self._mega: Optional[Mega] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._logged_in = False
    
    async def _ensure_connected(self):
        """Ensure MEGA connection is established"""
        if self._mega is None:
            self._mega = Mega()
            
            if Config.has_mega_credentials():
                # Login with credentials
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    lambda: self._mega.login(Config.MEGA_EMAIL, Config.MEGA_PASSWORD)
                )
                self._logged_in = True
            else:
                # Anonymous login for public folders
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._mega.login_anonymous
                )
    
    async def get_folder_files(self, folder_link: str) -> List[Dict[str, Any]]:
        """
        Get list of files in a MEGA folder
        
        Returns:
            List of file info dicts with keys: name, size, handle
        """
        await self._ensure_connected()
        
        loop = asyncio.get_event_loop()
        
        def fetch_folder():
            try:
                # Import folder
                folder = self._mega.get_public_folder_files(folder_link)
                
                files = []
                for handle, info in folder.items():
                    # Only include files, not folders
                    if info.get('t', 0) == 0:  # t=0 means file
                        files.append({
                            'handle': handle,
                            'name': info.get('a', {}).get('n', f'file_{handle}'),
                            'size': info.get('s', 0),
                        })
                
                # Sort by name for consistent ordering
                files.sort(key=lambda x: x['name'].lower())
                
                return files
            
            except Exception as e:
                error_msg = str(e).lower()
                if 'quota' in error_msg or 'bandwidth' in error_msg:
                    raise MegaQuotaError("MEGA bandwidth quota exceeded")
                raise MegaDownloadError(f"Failed to fetch folder: {e}")
        
        return await loop.run_in_executor(self._executor, fetch_folder)
    
    @retry(
        stop=stop_after_attempt(Config.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type(MegaQuotaError)
    )
    async def download_file(
        self,
        folder_link: str,
        file_handle: str,
        output_path: Path,
        progress_callback: Optional[Callable[[int], Any]] = None
    ) -> Path:
        """
        Download a single file from MEGA folder
        
        Args:
            folder_link: MEGA folder URL
            file_handle: File handle from get_folder_files
            output_path: Where to save the file
            progress_callback: Async callback(bytes_downloaded)
        
        Returns:
            Path to downloaded file
        """
        await self._ensure_connected()
        
        loop = asyncio.get_event_loop()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Progress tracking
        last_progress = [0]
        
        def download_with_progress():
            try:
                # Get folder files again to get the download URL
                folder_files = self._mega.get_public_folder_files(folder_link)
                
                if file_handle not in folder_files:
                    raise MegaDownloadError(f"File handle {file_handle} not found in folder")
                
                file_info = folder_files[file_handle]
                file_url = self._mega.get_public_file_url(file_handle, folder_link)
                
                # Download the file
                self._mega.download_url(
                    file_url,
                    dest_path=str(output_path.parent),
                    dest_filename=output_path.name
                )
                
                return output_path
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'quota' in error_msg or 'bandwidth' in error_msg or 'over' in error_msg:
                    raise MegaQuotaError("MEGA bandwidth quota exceeded")
                raise MegaDownloadError(f"Download failed: {e}")
        
        # Run download in thread
        result = await loop.run_in_executor(self._executor, download_with_progress)
        
        # Final progress callback
        if progress_callback and result.exists():
            await progress_callback(result.stat().st_size)
        
        return result
    
    async def download_file_simple(
        self,
        folder_link: str,
        file_handle: str,
        output_path: Path,
        file_size: int,
        progress_callback: Optional[Callable[[int], Any]] = None
    ) -> Path:
        """
        Simplified download using direct file download from public folder
        """
        await self._ensure_connected()
        
        loop = asyncio.get_event_loop()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        def do_download():
            try:
                # For public folders, we need to use import_public_folder first
                folder_data = self._mega.get_public_folder_files(folder_link)
                
                if file_handle not in folder_data:
                    raise MegaDownloadError(f"File not found: {file_handle}")
                
                # Download using the folder context
                file_info = folder_data[file_handle]
                filename = file_info.get('a', {}).get('n', 'unknown')
                
                # Use mega.py's download from public folder
                self._mega.download_public_file(
                    file_handle,
                    folder_link,
                    dest_path=str(output_path.parent),
                    dest_filename=output_path.name
                )
                
                return output_path
                
            except AttributeError:
                # Fallback for older mega.py versions
                return self._download_fallback(folder_link, file_handle, output_path)
            except Exception as e:
                error_msg = str(e).lower()
                if any(x in error_msg for x in ['quota', 'bandwidth', 'over quota']):
                    raise MegaQuotaError("MEGA bandwidth quota exceeded")
                raise MegaDownloadError(f"Download failed: {e}")
        
        result = await loop.run_in_executor(self._executor, do_download)
        
        # Progress callback with final size
        if progress_callback:
            await progress_callback(file_size)
        
        return result
    
    def _download_fallback(self, folder_link: str, file_handle: str, output_path: Path) -> Path:
        """Fallback download method for compatibility"""
        import requests
        from Crypto.Cipher import AES
        from Crypto.Util import Counter
        import base64
        import struct
        
        # This is a simplified fallback - the main method should work with mega.py
        folder_files = self._mega.get_public_folder_files(folder_link)
        
        if file_handle not in folder_files:
            raise MegaDownloadError(f"File not found: {file_handle}")
        
        file_info = folder_files[file_handle]
        
        # Get download URL and key
        # Note: This requires proper implementation based on mega.py internals
        # For production, ensure mega.py version supports public folder downloads
        
        raise MegaDownloadError("Fallback download not fully implemented - update mega.py")
    
    async def close(self):
        """Close downloader and cleanup"""
        self._executor.shutdown(wait=False)
        self._mega = None
        self._logged_in = False
