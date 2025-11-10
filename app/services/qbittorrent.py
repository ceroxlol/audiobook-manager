import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
import logging
from urllib.parse import urlencode
import time

from ..config import config

logger = logging.getLogger(__name__)

class QBittorrentClient:
    def __init__(self):
        self.base_url = f"http://{config.get('integrations.qbittorrent.host')}:{config.get('integrations.qbittorrent.port')}"
        self.username = config.get('integrations.qbittorrent.username')
        self.password = config.get('integrations.qbittorrent.password')
        self.session = None
        self.cookies = None
        self._login_time = 0
        self._login_ttl = 3600  # 1 hour
    
    async def __aenter__(self):
        await self.login()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _ensure_login(self):
        """Ensure we have a valid login session"""
        if time.time() - self._login_time > self._login_ttl:
            await self.login()
    
    async def login(self) -> bool:
        """Login to qBittorrent"""
        if self.session:
            await self.session.close()
        
        self.session = aiohttp.ClientSession()
        
        login_data = {
            'username': self.username,
            'password': self.password
        }
        
        try:
            async with self.session.post(f"{self.base_url}/api/v2/auth/login", 
                                       data=login_data, 
                                       timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    if text == "Ok.":
                        self.cookies = response.cookies
                        self._login_time = time.time()
                        logger.info("Successfully logged into qBittorrent")
                        return True
                    else:
                        logger.error(f"Login failed: {text}")
                        return False
                else:
                    logger.error(f"Login failed with status: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to qBittorrent API"""
        await self._ensure_login()
        
        url = f"{self.base_url}/api/v2/{endpoint}"
        
        try:
            async with self.session.request(method, url, cookies=self.cookies, **kwargs) as response:
                if response.status == 403:
                    # Session expired, try to re-login
                    logger.warning("Session expired, re-authenticating")
                    if await self.login():
                        # Retry the request
                        async with self.session.request(method, url, cookies=self.cookies, **kwargs) as retry_response:
                            return await self._handle_response(retry_response)
                    else:
                        raise Exception("Re-authentication failed")
                else:
                    return await self._handle_response(response)
        except Exception as e:
            logger.error(f"qBittorrent API request failed: {e}")
            raise
    
    async def _handle_response(self, response) -> Any:
        """Handle API response"""
        if response.status == 200:
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                return await response.json()
            else:
                text = await response.text()
                return text
        else:
            error_text = await response.text()
            logger.error(f"API error {response.status}: {error_text}")
            raise Exception(f"qBittorrent API error: {response.status} - {error_text}")
    
    async def add_torrent(self, 
                         torrent_url: str, 
                         category: str = "audiobooks",
                         save_path: str = None,
                         tags: List[str] = None) -> bool:
        """
        Add a torrent to qBittorrent
        
        Args:
            torrent_url: Magnet URL or torrent file URL
            category: Category to assign
            save_path: Custom save path
            tags: List of tags to apply
        """
        if not save_path:
            save_path = config.get('storage.download_path')
        
        data = {
            'urls': torrent_url,
            'category': category,
            'savepath': save_path,
            'paused': 'false'
        }
        
        if tags:
            data['tags'] = ','.join(tags)
        
        try:
            result = await self._make_request('post', 'torrents/add', data=data)
            logger.info(f"Successfully added torrent: {torrent_url[:100]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to add torrent: {e}")
            return False
    
    async def get_torrents(self, 
                          hashes: List[str] = None,
                          category: str = None,
                          tag: str = None) -> List[Dict[str, Any]]:
        """Get torrents with optional filtering"""
        params = {}
        if hashes:
            params['hashes'] = '|'.join(hashes)
        if category:
            params['category'] = category
        if tag:
            params['tag'] = tag
        
        try:
            torrents = await self._make_request('get', 'torrents/info', params=params)
            return torrents or []
        except Exception as e:
            logger.error(f"Failed to get torrents: {e}")
            return []
    
    async def get_torrent(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """Get specific torrent by hash"""
        torrents = await self.get_torrents(hashes=[torrent_hash])
        return torrents[0] if torrents else None
    
    async def delete_torrent(self, 
                           torrent_hash: str, 
                           delete_files: bool = True) -> bool:
        """Delete a torrent"""
        data = {
            'hashes': torrent_hash,
            'deleteFiles': str(delete_files).lower()
        }
        
        try:
            result = await self._make_request('post', 'torrents/delete', data=data)
            logger.info(f"Deleted torrent: {torrent_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete torrent: {e}")
            return False
    
    async def get_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get all categories"""
        try:
            categories = await self._make_request('get', 'torrents/categories')
            return categories
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            return {}
    
    async def create_category(self, 
                            name: str, 
                            save_path: str = None) -> bool:
        """Create a new category"""
        if not save_path:
            save_path = config.get('storage.download_path')
        
        params = {
            'category': name,
            'savePath': save_path
        }
        
        try:
            result = await self._make_request('post', 'torrents/createCategory', params=params)
            logger.info(f"Created category: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create category: {e}")
            return False
    
    async def ensure_audiobooks_category(self) -> bool:
        """Ensure audiobooks category exists with correct path"""
        try:
            categories = await self.get_categories()
            target_path = config.get('storage.download_path')
            
            if 'audiobooks' not in categories:
                logger.info(f"Creating audiobooks category with path: {target_path}")
                return await self.create_category('audiobooks', target_path)
            else:
                current_path = categories['audiobooks'].get('savePath', '')
                logger.debug(f"Audiobooks category exists with path: {current_path}")
                
                # If path is different, we can't easily update it in qBittorrent
                # Just log a warning and continue - the category exists which is what matters
                if current_path != target_path:
                    logger.warning(f"Audiobooks category path ({current_path}) differs from config ({target_path}). "
                                 f"Torrents will be saved to the category's existing path.")
                return True
        except Exception as e:
            logger.error(f"Failed to ensure audiobooks category: {e}")
            # Don't fail the download if category check fails - qBittorrent will use default
            return True
    
    async def get_download_speed(self) -> float:
        """Get current download speed in bytes/s"""
        try:
            data = await self._make_request('get', 'transfer/info')
            return data.get('dl_info_speed', 0)
        except Exception as e:
            logger.error(f"Failed to get download speed: {e}")
            return 0
    
    async def test_connection(self) -> bool:
        """Test connection to qBittorrent"""
        try:
            await self._ensure_login()
            # Try to get application version
            version = await self._make_request('get', 'app/version')
            return version is not None
        except Exception as e:
            logger.error(f"qBittorrent connection test failed: {e}")
            return False

# Singleton instance
qbittorrent_client = QBittorrentClient()
