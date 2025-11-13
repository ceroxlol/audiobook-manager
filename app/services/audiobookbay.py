import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin
import logging
import re
from bs4 import BeautifulSoup

from ..config import config

logger = logging.getLogger(__name__)

class AudiobookBayClient:
    def __init__(self):
        self.enabled = config.get('integrations.audiobookbay.enabled', True)
        self.domain = config.get('integrations.audiobookbay.domain', 'audiobookbay.lu')
        self.base_url = f"https://{self.domain}"
        self.session = None
        logger.info(f"AudiobookBay client initialized for {self.base_url}")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, url: str, params: Dict = None) -> Optional[str]:
        """Make HTTP request and return HTML content"""
        if not self.session:
            async with aiohttp.ClientSession() as session:
                return await self._make_request_with_session(session, url, params)
        else:
            return await self._make_request_with_session(self.session, url, params)
    
    async def _make_request_with_session(self, session: aiohttp.ClientSession, url: str, params: Dict = None) -> Optional[str]:
        """Make request with existing session"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            logger.debug(f"Making request to: {url}")
            
            async with session.get(url, params=params, headers=headers, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"AudiobookBay request failed: {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"AudiobookBay request timed out: {url}")
            return None
        except Exception as e:
            logger.error(f"Error making request to AudiobookBay: {e}")
            return None
    
    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for audiobooks on AudiobookBay
        
        Args:
            query: Search query
        """
        if not self.enabled:
            logger.info("AudiobookBay is disabled in configuration")
            return []
        
        try:
            # Construct search URL
            search_url = f"{self.base_url}/page/1/"
            params = {'s': query}
            
            logger.info(f"Searching AudiobookBay for: {query}")
            
            # Get search results page
            html = await self._make_request(search_url, params)
            if not html:
                logger.warning("No response from AudiobookBay")
                return []
            
            # Parse results
            results = await self._parse_search_results(html, query)
            
            logger.info(f"Found {len(results)} results from AudiobookBay")
            return results
            
        except Exception as e:
            logger.error(f"AudiobookBay search failed: {e}")
            return []
    
    async def _parse_search_results(self, html: str, query: str) -> List[Dict[str, Any]]:
        """Parse search results HTML"""
        results = []
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Find all audiobook entries
            # AudiobookBay typically uses post divs with specific classes
            posts = soup.find_all('div', class_='post')
            
            if not posts:
                # Try alternative selectors
                posts = soup.find_all('article')
            
            logger.debug(f"Found {len(posts)} post elements")
            
            for post in posts:
                try:
                    result = await self._parse_single_result(post, query)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"Failed to parse individual result: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Failed to parse AudiobookBay search results: {e}")
        
        return results
    
    async def _parse_single_result(self, post_element, query: str) -> Optional[Dict[str, Any]]:
        """Parse a single audiobook result"""
        try:
            # Extract title
            title_elem = post_element.find('div', class_='postTitle') or post_element.find('h2', class_='postTitle')
            if not title_elem:
                title_elem = post_element.find('a', class_='post-title')
            
            if not title_elem:
                return None
            
            title_link = title_elem.find('a')
            if not title_link:
                return None
            
            title = title_link.get_text(strip=True)
            detail_url = title_link.get('href', '')
            
            # Make sure we have absolute URL
            if detail_url and not detail_url.startswith('http'):
                detail_url = urljoin(self.base_url, detail_url)
            
            # Extract metadata from post content
            content = post_element.get_text()
            
            # Extract author (often in format "Author: Name" or "by Name")
            author = self._extract_author(title, content)
            
            # Extract narrator
            narrator = self._extract_narrator(content)
            
            # Extract format and quality
            format_info = self._extract_format(title, content)
            quality = self._extract_quality(content)
            
            # Extract size (often in format like "Size: 123 MB")
            size = self._extract_size(content)
            
            # Get magnet link (need to fetch detail page)
            magnet_url = await self._get_magnet_link(detail_url)
            
            if not magnet_url:
                logger.debug(f"No magnet link found for: {title}")
                return None
            
            # Calculate score
            score = self._calculate_result_score(title, format_info, size)
            
            return {
                'id': None,  # Will be assigned by database
                'title': title,
                'author': author,
                'narrator': narrator,
                'size': size,
                'seeders': 0,  # AudiobookBay doesn't show seeders on search page
                'leechers': 0,
                'download_url': '',  # No direct download
                'magnet_url': magnet_url,
                'indexer': 'AudiobookBay',
                'quality': quality,
                'format': format_info,
                'score': score,
                'age': 0,  # AudiobookBay doesn't consistently show dates
                'languages': self._extract_languages(title, content)
            }
            
        except Exception as e:
            logger.debug(f"Error parsing single result: {e}")
            return None
    
    async def _get_magnet_link(self, detail_url: str) -> Optional[str]:
        """Fetch detail page and extract magnet link"""
        try:
            if not detail_url:
                return None
            
            html = await self._make_request(detail_url)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for magnet link
            magnet_link = soup.find('a', href=re.compile(r'^magnet:\?'))
            
            if magnet_link:
                return magnet_link.get('href')
            
            # Alternative: look for any link containing 'magnet:'
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if href.startswith('magnet:'):
                    return href
            
            logger.debug(f"No magnet link found in detail page: {detail_url}")
            return None
            
        except Exception as e:
            logger.debug(f"Error fetching magnet link from {detail_url}: {e}")
            return None
    
    def _extract_author(self, title: str, content: str) -> str:
        """Extract author name from title or content"""
        # Try to find author in content
        author_patterns = [
            r'Author[:\s]+([^\n]+)',
            r'Written by[:\s]+([^\n]+)',
            r'by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        
        for pattern in author_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                author = match.group(1).strip()
                # Clean up author name
                author = re.sub(r'[\[\(].*?[\]\)]', '', author).strip()
                if len(author) > 3 and len(author) < 100:
                    return author
        
        # Try to extract from title (format: "Book Title - Author Name")
        if ' - ' in title or ' – ' in title:
            parts = re.split(r'\s+[-–]\s+', title)
            if len(parts) >= 2:
                author_candidate = parts[-1].strip()
                # Remove common suffixes
                author_candidate = re.sub(r'\s+\(.*?\)$', '', author_candidate)
                author_candidate = re.sub(r'\s+\[.*?\]$', '', author_candidate)
                if len(author_candidate) > 3 and len(author_candidate) < 100:
                    return author_candidate
        
        return "Unknown Author"
    
    def _extract_narrator(self, content: str) -> str:
        """Extract narrator name from content"""
        narrator_patterns = [
            r'Narrator[:\s]+([^\n]+)',
            r'Read by[:\s]+([^\n]+)',
            r'Narrated by[:\s]+([^\n]+)',
        ]
        
        for pattern in narrator_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                narrator = match.group(1).strip()
                narrator = re.sub(r'[\[\(].*?[\]\)]', '', narrator).strip()
                if len(narrator) > 3 and len(narrator) < 100:
                    return narrator
        
        return "Unknown Narrator"
    
    def _extract_format(self, title: str, content: str) -> str:
        """Extract file format"""
        text = (title + ' ' + content).lower()
        
        if 'm4b' in text:
            return 'M4B'
        elif 'mp3' in text:
            return 'MP3'
        elif 'flac' in text:
            return 'FLAC'
        elif 'm4a' in text:
            return 'M4A'
        else:
            return 'Unknown'
    
    def _extract_quality(self, content: str) -> str:
        """Extract quality information"""
        quality_patterns = [
            r'(\d+)\s*kbps',
            r'(\d+)\s*kb/s',
        ]
        
        for pattern in quality_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return f"{match.group(1)}kbps"
        
        if 'flac' in content.lower() or 'lossless' in content.lower():
            return 'FLAC'
        
        return 'Unknown'
    
    def _extract_size(self, content: str) -> int:
        """Extract file size in bytes"""
        size_patterns = [
            r'Size[:\s]+([0-9.]+)\s*(MB|GB)',
            r'([0-9.]+)\s*(MB|GB)',
        ]
        
        for pattern in size_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                size_value = float(match.group(1))
                unit = match.group(2).upper()
                
                if unit == 'GB':
                    return int(size_value * 1024 * 1024 * 1024)
                elif unit == 'MB':
                    return int(size_value * 1024 * 1024)
        
        return 0
    
    def _extract_languages(self, title: str, content: str) -> List[str]:
        """Extract languages from title or content"""
        text = (title + ' ' + content).lower()
        languages = []
        
        language_keywords = {
            'english': ['english', 'eng'],
            'german': ['german', 'deutsch', 'ger'],
            'french': ['french', 'français', 'fr'],
            'spanish': ['spanish', 'español', 'sp'],
        }
        
        for lang, keywords in language_keywords.items():
            if any(keyword in text for keyword in keywords):
                languages.append(lang)
        
        return languages if languages else ['English']  # Default to English
    
    def _calculate_result_score(self, title: str, format_info: str, size: int) -> float:
        """Calculate a score for ranking results"""
        score = 50.0  # Base score for AudiobookBay results
        
        # Format preferences
        if format_info == 'M4B':
            score += 20
        elif format_info == 'FLAC':
            score += 15
        elif format_info == 'MP3':
            score += 10
        
        # Size preferences (reasonable audiobook sizes)
        if 50 * 1024 * 1024 < size < 500 * 1024 * 1024:  # 50MB - 500MB
            score += 15
        elif 500 * 1024 * 1024 < size < 2 * 1024 * 1024 * 1024:  # 500MB - 2GB
            score += 25
        elif size > 2 * 1024 * 1024 * 1024:  # Over 2GB
            score += 5
        
        # AudiobookBay is a trusted source
        score += 15
        
        return score
    
    async def test_connection(self) -> bool:
        """Test connection to AudiobookBay"""
        try:
            html = await self._make_request(self.base_url)
            return html is not None and len(html) > 0
        except Exception as e:
            logger.error(f"AudiobookBay connection test failed: {e}")
            return False

# Singleton instance
audiobookbay_client = AudiobookBayClient()
