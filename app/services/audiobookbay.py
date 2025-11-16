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
        
        # Support both old 'domain' and new 'domains' config
        domains_config = config.get('integrations.audiobookbay.domains', None)
        if domains_config and isinstance(domains_config, list):
            self.domains = domains_config
        else:
            # Fallback to old single domain config
            single_domain = config.get('integrations.audiobookbay.domain', 'audiobookbay.lu')
            self.domains = [single_domain]
        
        self.timeout = config.get('integrations.audiobookbay.timeout', 10)  # Default 10 seconds
        self.current_domain = None  # Will be set on first successful connection
        self.session = None
        
        logger.info(f"AudiobookBay client initialized with {len(self.domains)} domain(s): {', '.join(self.domains)} (timeout: {self.timeout}s)")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_base_url(self, domain: str) -> str:
        """Get base URL for a domain"""
        return f"https://{domain}"
    
    async def _try_domains(self, url_path: str, params: Dict = None) -> Optional[tuple]:
        """
        Try each domain in sequence until one succeeds
        Returns tuple of (html_content, successful_domain) or None
        """
        # Try current domain first if we have one
        domains_to_try = []
        if self.current_domain:
            domains_to_try.append(self.current_domain)
            # Add other domains after current one
            domains_to_try.extend([d for d in self.domains if d != self.current_domain])
        else:
            domains_to_try = self.domains.copy()
        
        for domain in domains_to_try:
            base_url = self._get_base_url(domain)
            full_url = f"{base_url}{url_path}"
            
            logger.debug(f"Trying domain: {domain}")
            html = await self._make_request_direct(full_url, params)
            
            if html:
                # Success! Remember this domain
                if self.current_domain != domain:
                    logger.info(f"AudiobookBay: Switched to working domain: {domain}")
                    self.current_domain = domain
                return (html, domain)
            else:
                logger.debug(f"Domain {domain} failed, trying next...")
        
        logger.error(f"All AudiobookBay domains failed. Tried: {', '.join(domains_to_try)}")
        return None
    
    async def _make_request(self, url_path: str, params: Dict = None) -> Optional[str]:
        """
        Make HTTP request with domain fallback
        url_path should be the path after domain (e.g., "/" or "/page/1/")
        """
        result = await self._try_domains(url_path, params)
        if result:
            return result[0]  # Return just the HTML content
        return None
    
    async def _make_request_direct(self, url: str, params: Dict = None) -> Optional[str]:
        """Make HTTP request to a specific URL without domain fallback"""
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
            
            # Build the full URL with parameters for logging
            if params:
                param_str = '&'.join([f"{k}={quote(str(v))}" for k, v in params.items()])
                full_url = f"{url}?{param_str}"
            else:
                full_url = url
            
            logger.debug(f"Making request to: {full_url}")
            
            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    logger.debug(f"Request successful: {full_url}")
                    return await response.text()
                else:
                    logger.error(f"AudiobookBay request failed with status {response.status}: {full_url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"AudiobookBay request timed out after {self.timeout}s: {url}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"AudiobookBay client error at {url}: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making request to AudiobookBay at {url}: {type(e).__name__}: {e}")
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
            # Construct search URL - AudiobookBay uses WordPress search format
            # The search URL should be: https://domain.com/?s=query
            url_path = "/"
            params = {'s': query}
            
            logger.info(f"Searching AudiobookBay for: '{query}'")
            
            # Get search results page (with domain fallback)
            html = await self._make_request(url_path, params)
            if not html:
                logger.warning(f"No response from any AudiobookBay domain for query: '{query}'")
                return []
            
            # Parse results
            results = await self._parse_search_results(html, query)
            
            logger.info(f"Found {len(results)} results from AudiobookBay (domain: {self.current_domain}) for query: '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"AudiobookBay search failed for query '{query}': {e}")
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
                # Use current working domain
                base_url = self._get_base_url(self.current_domain) if self.current_domain else self._get_base_url(self.domains[0])
                detail_url = urljoin(base_url, detail_url)
            
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
            
            logger.debug(f"Fetching magnet link from: {detail_url}")
            
            # Use _make_request_direct since we have a full URL
            html = await self._make_request_direct(detail_url)
            if not html:
                logger.debug(f"No HTML content received from: {detail_url}")
                return None
            
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for magnet link
            magnet_link = soup.find('a', href=re.compile(r'^magnet:\?'))
            
            if magnet_link:
                magnet = magnet_link.get('href')
                logger.debug(f"Found magnet link at {detail_url}")
                return magnet
            
            # Alternative: look for any link containing 'magnet:'
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if href.startswith('magnet:'):
                    logger.debug(f"Found magnet link (alternative search) at {detail_url}")
                    return href
            
            logger.debug(f"No magnet link found in detail page: {detail_url}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching magnet link from {detail_url}: {type(e).__name__}: {e}")
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
        """Test connection to AudiobookBay (tries all domains)"""
        if not self.enabled:
            logger.info("AudiobookBay is disabled in configuration")
            return False
        
        try:
            logger.debug(f"Testing connection to AudiobookBay domains: {', '.join(self.domains)}")
            
            # Try domains with fallback
            result = await self._try_domains("/")
            
            if result:
                html, domain = result
                logger.info(f"AudiobookBay connection test successful: {domain}")
                return True
            else:
                logger.warning(f"AudiobookBay connection test failed: all domains unreachable")
                return False
        except Exception as e:
            logger.error(f"AudiobookBay connection test failed: {type(e).__name__}: {e}")
            return False
    
    def get_active_domain(self) -> Optional[str]:
        """Get the currently active domain (or None if not yet determined)"""
        return self.current_domain

# Singleton instance
audiobookbay_client = AudiobookBayClient()
