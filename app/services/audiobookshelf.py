import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
import logging
import os
import json
from pathlib import Path

from ..config import config

logger = logging.getLogger(__name__)

class AudiobookshelfClient:
    def __init__(self):
        self.base_url = f"http://{config.get('integrations.audiobookshelf.host')}:{config.get('integrations.audiobookshelf.port')}"
        self.api_key = config.get('integrations.audiobookshelf.api_key')
        self.session = None
        
        logger.debug(f"Audiobookshelf client initialized for {self.base_url}")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers={'Authorization': f'Bearer {self.api_key}'})
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to Audiobookshelf API"""
        if not self.session:
            async with aiohttp.ClientSession(headers={'Authorization': f'Bearer {self.api_key}'}) as session:
                return await self._make_request_with_session(session, endpoint, method, **kwargs)
        else:
            return await self._make_request_with_session(self.session, endpoint, method, **kwargs)
    
    async def _make_request_with_session(self, session: aiohttp.ClientSession, endpoint: str, method: str, **kwargs) -> Any:
        """Make request with existing session"""
        url = f"{self.base_url}/{endpoint}"
        
        # Ensure JSON content type for POST/PUT requests
        if method.lower() in ['post', 'put'] and 'json' in kwargs:
            kwargs['headers'] = kwargs.get('headers', {})
            kwargs['headers']['Content-Type'] = 'application/json'
        
        logger.debug(f"Making {method.upper()} request to {url}")
        
        try:
            async with session.request(method, url, timeout=30, **kwargs) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        data = await response.json()
                        logger.debug(f"API response: {data}")
                        return data
                    else:
                        text = await response.text()
                        logger.debug(f"API response text: {text}")
                        return text
                else:
                    error_text = await response.text()
                    logger.error(f"Audiobookshelf API error {response.status}: {error_text}")
                    raise Exception(f"Audiobookshelf API error: {response.status} - {error_text}")
                    
        except Exception as e:
            logger.error(f"Audiobookshelf API request failed: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """Test connection to Audiobookshelf"""
        try:
            # Try to get libraries list
            libraries = await self.get_libraries()
            return libraries is not None
        except Exception as e:
            logger.error(f"Audiobookshelf connection test failed: {e}")
            return False
    
    async def get_libraries(self) -> List[Dict[str, Any]]:
        """Get all libraries from Audiobookshelf"""
        try:
            libraries = await self._make_request('get', 'api/libraries')
            return libraries.get('libraries', [])
        except Exception as e:
            logger.error(f"Failed to get libraries: {e}")
            return []
    
    async def scan_library(self, library_id: str) -> bool:
        """Trigger a library scan"""
        try:
            result = await self._make_request('post', f'api/libraries/{library_id}/scan')
            logger.info(f"Triggered library scan for {library_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to scan library {library_id}: {e}")
            return False
    
    async def get_library_items(self, library_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get items from a specific library"""
        try:
            params = {'limit': limit}
            result = await self._make_request('get', f'api/libraries/{library_id}/items', params=params)
            return result.get('results', [])
        except Exception as e:
            logger.error(f"Failed to get library items for {library_id}: {e}")
            return []
    
    async def find_audiobook_by_title(self, title: str, author: str = None) -> Optional[Dict[str, Any]]:
        """Find an audiobook by title and optionally author"""
        try:
            libraries = await self.get_libraries()
            
            for library in libraries:
                items = await self.get_library_items(library['id'])
                
                for item in items:
                    item_title = item.get('media', {}).get('metadata', {}).get('title', '').lower()
                    item_author = item.get('media', {}).get('metadata', {}).get('authorName', '').lower()
                    
                    search_title = title.lower()
                    search_author = author.lower() if author else None
                    
                    # Check title match
                    title_match = search_title in item_title or item_title in search_title
                    
                    # If author provided, check author match
                    if search_author:
                        author_match = search_author in item_author or item_author in search_author
                        if title_match and author_match:
                            return item
                    elif title_match:
                        return item
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find audiobook {title}: {e}")
            return None
    
    async def add_item_to_library(self, 
                                library_id: str, 
                                folder_path: str, 
                                title: str,
                                author: str = None,
                                series: str = None) -> Optional[Dict[str, Any]]:
        """
        Add a new item to Audiobookshelf library
        
        Args:
            library_id: ID of the library to add to
            folder_path: Path to the audiobook folder
            title: Book title
            author: Book author
            series: Series name (optional)
        """
        try:
            # Verify the path exists
            if not os.path.exists(folder_path):
                logger.error(f"Path does not exist: {folder_path}")
                return None
            
            data = {
                'path': folder_path,
                'libraryId': library_id
            }
            
            # Add metadata if provided
            if title or author or series:
                data['metadata'] = {}
                if title:
                    data['metadata']['title'] = title
                if author:
                    data['metadata']['author'] = author
                if series:
                    data['metadata']['series'] = series
            
            result = await self._make_request('post', 'api/items', json=data)
            logger.info(f"Successfully added audiobook to library: {title}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to add item to library: {e}")
            return None

# Singleton instance
audiobookshelf_client = AudiobookshelfClient()