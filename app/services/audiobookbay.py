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
        self.username = config.get('integrations.audiobookbay.username', '')
        self.password = config.get('integrations.audiobookbay.password', '')
        self.current_base_url = None  # Will store successful protocol+domain (e.g., "http://audiobookbay.fi")
        self.logged_in = False
        self.session = None
        
        logger.info(f"AudiobookBay client initialized with {len(self.domains)} domain(s): {', '.join(self.domains)} (timeout: {self.timeout}s, login: {'enabled' if self.username else 'disabled'})")
    
    async def __aenter__(self):
        # Use unsafe cookie jar to handle cross-domain cookies properly
        jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(cookie_jar=jar)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_base_url_from_domain(self, domain: str, protocol: str = "https") -> str:
        """Get base URL for a domain with specified protocol"""
        return f"{protocol}://{domain}"
    
    async def _try_domains_parallel(self, url_path: str, params: Dict = None) -> Optional[tuple]:
        """
        Try current domain first, then try all other domains in parallel if it fails
        Returns tuple of (html_content, successful_base_url) or None
        """
        # If we have a working base URL, try it first exclusively
        if self.current_base_url:
            current_url = f"{self.current_base_url}{url_path}"
            logger.debug(f"Trying current AudiobookBay URL: {current_url}")
            try:
                html = await self._make_request_direct(current_url, params)
                if html:
                    logger.debug(f"Current domain still working: {self.current_base_url}")
                    return (html, self.current_base_url)
                else:
                    # Current domain failed, reset and try alternatives
                    logger.warning(f"Current domain {self.current_base_url} failed, resetting and trying alternatives")
                    self.current_base_url = None
                    self.logged_in = False
            except Exception as e:
                # Current domain had an error, reset and try alternatives
                logger.warning(f"Current domain {self.current_base_url} error: {type(e).__name__}: {e}. Resetting and trying alternatives")
                self.current_base_url = None
                self.logged_in = False
        
        # Build list of alternative URLs to try (only if current failed or not set)
        urls_to_try = []
        for domain in self.domains:
            for protocol in ['http', 'https']:
                base_url = self._get_base_url_from_domain(domain, protocol)
                full_url = f"{base_url}{url_path}"
                urls_to_try.append((full_url, base_url))
        logger.info(f"Testing {len(urls_to_try)} AudiobookBay URLs in parallel (HTTP preferred): {[url for url, _ in urls_to_try]}")

        async def try_url(url: str, base_url: str):
            try:
                html = await self._make_request_direct(url, params)
                if html:
                    return (html, base_url)
            except Exception as e:
                logger.debug(f"Failed to fetch {url}: {type(e).__name__}")
            return None

        tasks = [try_url(url, base) for url, base in urls_to_try]

        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                html, successful_base_url = result
                logger.info(f"AudiobookBay: Found working URL: {successful_base_url}")
                self.current_base_url = successful_base_url
                
                # Try to login if credentials are configured and not already logged in
                if self.username and self.password and not self.logged_in:
                    await self._login()
                
                return result

        logger.error(f"All AudiobookBay URLs failed. Tried {len(urls_to_try)} combinations")
        self.current_base_url = None
        self.logged_in = False
        return None
    
    async def _make_request(self, url_path: str, params: Dict = None) -> Optional[str]:
        """
        Make HTTP request with domain fallback
        url_path should be the path after domain (e.g., "/" or "/page/1/")
        """
        result = await self._try_domains_parallel(url_path, params)
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
            # Convert query to lowercase to avoid nginx issues
            url_path = "/"
            params = {'s': query.lower(), 'cat': 'undefined,undefined'}
            
            logger.info(f"Searching AudiobookBay for: '{query}' (lowercase: '{query.lower()}', base URL: {self.current_base_url})")
            
            # Get search results page (with domain fallback)
            html = await self._make_request(url_path, params)
            if not html:
                logger.warning(f"No response from any AudiobookBay domain for query: '{query}'")
                return []
            
            # Parse results
            all_results = await self._parse_search_results(html, query)
            
            # Filter results to only include titles that match the search term
            # AudiobookBay returns many unrelated results (like top 100), so we filter by search term
            search_terms = query.lower().split()
            filtered_results = []
            for result in all_results:
                title_lower = result['title'].lower()
                # Check if any search term appears in the title
                if any(term in title_lower for term in search_terms):
                    filtered_results.append(result)
                else:
                    logger.debug(f"Filtered out result: '{result['title']}' (doesn't match search term '{query}')")
            
            logger.info(f"Found {len(filtered_results)} matching results (filtered from {len(all_results)} total) from AudiobookBay (base URL: {self.current_base_url}) for query: '{query}'")
            return filtered_results
            
        except Exception as e:
            logger.error(f"AudiobookBay search failed for query '{query}': {type(e).__name__}: {e}")
            # Domain reset is handled in _try_domains_parallel
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
                # Use current working base URL
                base_url = self.current_base_url if self.current_base_url else self._get_base_url_from_domain(self.domains[0])
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
            
            # Store detail URL instead of fetching magnet link during search
            # The magnet link will be fetched when user clicks download
            logger.debug(f"Storing detail URL for: {title}")
            
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
                'download_url': detail_url,  # Store detail URL here
                'magnet_url': '',  # Will be fetched during download
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
    
    async def download_torrent_file(self, detail_url: str, save_path: str) -> Optional[str]:
        """Download .torrent file from AudiobookBay detail page
        
        Args:
            detail_url: URL to the audiobook detail page
            save_path: Directory to save the .torrent file
            
        Returns:
            Path to downloaded .torrent file, or None if failed
        """
        try:
            if not detail_url:
                logger.error("No detail URL provided")
                return None
            
            logger.info(f"Fetching torrent download link from: {detail_url}")
            
            # Fetch the detail page
            html = await self._make_request_direct(detail_url)
            if not html:
                logger.error(f"No HTML content received from: {detail_url}")
                return None
            
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for torrent download link in the table row
            # Pattern: <a href='/downld0?downfs=...'>Torrent Free Downloads</a>
            torrent_link = soup.find('a', href=re.compile(r'^/downld0\?downfs='))
            
            if not torrent_link:
                logger.error(f"No torrent download link found at {detail_url}")
                return None
            
            torrent_path = torrent_link.get('href')
            # Make absolute URL - force HTTPS to match where cookies are set
            base_url = "https://audiobookbay.lu"  # Always use main domain with HTTPS
            torrent_url = urljoin(base_url, torrent_path)
            logger.info(f"Found torrent download URL: {torrent_url}")
            
            # Download the .torrent file directly from this URL
            import os
            os.makedirs(save_path, exist_ok=True)
            
            # Generate filename from detail URL
            import hashlib
            url_hash = hashlib.md5(detail_url.encode()).hexdigest()[:8]
            torrent_file_path = os.path.join(save_path, f"audiobook_{url_hash}.torrent")
            
            logger.info(f"Downloading .torrent file to: {torrent_file_path}")
            
            # Ensure we have a session (needed for authenticated downloads)
            if not self.session:
                jar = aiohttp.CookieJar(unsafe=True)
                self.session = aiohttp.ClientSession(cookie_jar=jar)
            
            # If we have credentials, ensure we're logged in before downloading
            if self.username and self.password and not self.logged_in:
                logger.info("Logging in before downloading torrent file")
                login_success = await self._login()
                if not login_success:
                    logger.error("Failed to login, torrent download may fail")
            
            # Download the torrent file - the /downld0?downfs=... link directly returns the .torrent file
            torrent_content = await self._download_file_with_session(self.session, torrent_url)
            
            if not torrent_content:
                logger.error(f"Failed to download torrent file from {torrent_url}")
                return None
            
            # Debug: Check what we actually downloaded
            logger.debug(f"Downloaded content size: {len(torrent_content)} bytes")
            logger.debug(f"Content starts with: {torrent_content[:100]}")
            
            # Check if it's HTML (login page or error page) instead of a torrent
            if torrent_content.startswith(b'<!DOCTYPE') or torrent_content.startswith(b'<html'):
                logger.error(f"Downloaded HTML instead of torrent file (likely login page or error)")
                logger.debug(f"HTML content preview: {torrent_content[:500].decode('utf-8', errors='ignore')}")
                return None
            
            # Verify it's a valid torrent file (should start with 'd' for bencoded data)
            if not torrent_content.startswith(b'd'):
                logger.error(f"Downloaded content is not a valid torrent file (doesn't start with 'd')")
                logger.debug(f"Content preview: {torrent_content[:200]}")
                return None
            
            # Save the torrent file
            with open(torrent_file_path, 'wb') as f:
                f.write(torrent_content)
            
            # Verify the file was saved correctly
            if not os.path.exists(torrent_file_path) or not torrent_file_path.endswith('.torrent'):
                logger.error(f"Failed to save torrent file properly: {torrent_file_path}")
                return None
            
            logger.info(f"Successfully downloaded .torrent file ({len(torrent_content)} bytes): {torrent_file_path}")
            return torrent_file_path
            
        except Exception as e:
            logger.error(f"Error downloading torrent file from {detail_url}: {type(e).__name__}: {e}")
            return None
    
    async def _download_file_with_session(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """Download a file and return its content as bytes"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            # Log session cookies before request
            all_cookies = list(session.cookie_jar)
            logger.debug(f"Making download request with {len(all_cookies)} total cookies in jar")
            if all_cookies:
                logger.debug(f"Cookies: {[(c.key, c['domain']) for c in all_cookies]}")
            
            # Follow redirects and handle potential login redirects
            async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
                logger.debug(f"Download response status: {response.status}, final URL: {response.url}")
                content = await response.read()
                
                # Check if we got a meta refresh redirect to login (common in AudiobookBay)
                if b'login.php' in content or b"<meta http-equiv='Refresh'" in content:
                    logger.warning(f"Download returned login redirect page")
                    
                    # If we have credentials and aren't logged in, try to login
                    if self.username and self.password:
                        logger.info("Detected login requirement, attempting to login")
                        # Force login even if we think we're logged in (session may have expired)
                        self.logged_in = False
                        login_success = await self._login()
                        if login_success:
                            # Verify cookies are present after login
                            all_cookies_after = list(session.cookie_jar)
                            logger.debug(f"Cookies after login: {len(all_cookies_after)} total cookies")
                            if all_cookies_after:
                                logger.debug(f"Cookie details after login: {[(c.key, c['domain']) for c in all_cookies_after]}")
                            
                            # Retry the download after login using the same session
                            logger.info("Login successful, retrying download")
                            async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as retry_response:
                                logger.debug(f"Retry response status: {retry_response.status}, final URL: {retry_response.url}")
                                if retry_response.status == 200:
                                    retry_content = await retry_response.read()
                                    # Verify we didn't get another login redirect
                                    if b'login.php' not in retry_content and b"<meta http-equiv='Refresh'" not in retry_content:
                                        logger.info("Download successful after login")
                                        return retry_content
                                    else:
                                        logger.error("Still getting login page after successful login")
                                        logger.debug(f"Retry content preview: {retry_content[:300]}")
                                        # Check cookies one more time
                                        final_cookies_all = list(session.cookie_jar)
                                        logger.debug(f"Cookies present during retry: {len(final_cookies_all)} total cookies")
                                        if final_cookies_all:
                                            logger.debug(f"Cookie details: {[(c.key, c['domain']) for c in final_cookies_all]}")
                                        return None
                                else:
                                    logger.error(f"Failed to download file after login: HTTP {retry_response.status}")
                                    return None
                        else:
                            logger.error("Login failed, cannot download torrent file")
                            return None
                    else:
                        logger.error("Download requires login but no credentials configured")
                        return None
                
                if response.status == 200:
                    return content
                else:
                    logger.error(f"Failed to download file: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error downloading file from {url}: {type(e).__name__}: {e}")
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
        """Test connection to AudiobookBay (tries all domains in parallel)"""
        if not self.enabled:
            logger.info("AudiobookBay is disabled in configuration")
            return False
        
        try:
            logger.debug(f"Testing connection to AudiobookBay domains: {', '.join(self.domains)}")
            
            # Try domains with parallel fallback
            result = await self._try_domains_parallel("/")
            
            if result:
                html, base_url = result
                logger.info(f"AudiobookBay connection test successful: {base_url}")
                return True
            else:
                logger.warning(f"AudiobookBay connection test failed: all domains unreachable")
                return False
        except Exception as e:
            logger.error(f"AudiobookBay connection test failed: {type(e).__name__}: {e}")
            return False
    
    def get_active_domain(self) -> Optional[str]:
        """Get the currently active base URL (or None if not yet determined)"""
        if self.current_base_url:
            # Extract just the domain from the full URL for display
            return self.current_base_url.replace('https://', '').replace('http://', '')
        return None
    
    def reset_domain(self):
        """Reset the current domain selection to force re-testing"""
        logger.info(f"Resetting AudiobookBay domain selection (was: {self.current_base_url})")
        self.current_base_url = None
        self.logged_in = False
    
    async def set_domain(self, domain: str, protocol: str = 'http') -> bool:
        """Manually set a specific domain and protocol"""
        if domain not in self.domains:
            logger.error(f"Domain {domain} not in configured domains list")
            return False
        
        base_url = self._get_base_url_from_domain(domain, protocol)
        logger.info(f"Manually setting AudiobookBay domain to: {base_url}")
        
        # Test the domain
        try:
            html = await self._make_request_direct(f"{base_url}/")
            if html:
                self.current_base_url = base_url
                logger.info(f"Domain {base_url} is working")
                
                # Try to login if credentials are configured
                if self.username and self.password:
                    await self._login()
                
                return True
            else:
                logger.warning(f"Domain {base_url} is not responding")
                return False
        except Exception as e:
            logger.error(f"Failed to test domain {base_url}: {e}")
            return False
    
    async def get_domain_statuses(self) -> List[Dict[str, Any]]:
        """Test all configured domains and return their status"""
        statuses = []
        
        for domain in self.domains:
            for protocol in ['http', 'https']:
                base_url = self._get_base_url_from_domain(domain, protocol)
                status = {
                    'domain': domain,
                    'protocol': protocol,
                    'url': base_url,
                    'working': False,
                    'current': self.current_base_url == base_url
                }
                
                try:
                    html = await self._make_request_direct(f"{base_url}/")
                    if html:
                        status['working'] = True
                except Exception as e:
                    status['error'] = str(e)
                
                statuses.append(status)
        
        return statuses
    
    async def _login(self) -> bool:
        """Login to AudiobookBay with configured credentials"""
        if not self.username or not self.password:
            logger.debug("No AudiobookBay credentials configured, skipping login")
            return False
        
        if not self.current_base_url:
            logger.warning("Cannot login: no working domain established")
            return False
        
        try:
            # Ensure we have a session with unsafe cookie jar to store cookies
            if not self.session:
                jar = aiohttp.CookieJar(unsafe=True)
                self.session = aiohttp.ClientSession(cookie_jar=jar)
            
            # Use the actual domain from the download URL (which may be https://audiobookbay.lu)
            # not necessarily the current_base_url
            login_base = "https://audiobookbay.lu"  # Always use the main domain for login
            logger.info(f"Attempting to login to AudiobookBay at {login_base}")
            
            # AudiobookBay login URL
            login_url = f"{login_base}/member/login.php"
            
            # Prepare login data
            login_data = {
                'log': self.username,
                'pwd': self.password,
                'wp-submit': 'Log In',
                'redirect_to': login_base,
                'testcookie': '1'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': login_url
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            # Use self.session to preserve cookies
            async with self.session.post(login_url, data=login_data, headers=headers, timeout=timeout, allow_redirects=True) as response:
                if response.status == 200:
                    # Check if login was successful by looking for error messages
                    html = await response.text()
                    if 'login_error' in html.lower() or 'incorrect' in html.lower():
                        logger.error("AudiobookBay login failed: incorrect username or password")
                        self.logged_in = False
                        return False
                    
                    # Log cookies for debugging
                    all_cookies = list(self.session.cookie_jar)
                    logger.info(f"AudiobookBay login successful - total cookies in jar: {len(all_cookies)}")
                    if all_cookies:
                        logger.debug(f"Cookie details: {[(c.key, c['domain'], c.value[:20] if len(c.value) > 20 else c.value) for c in all_cookies]}")
                    else:
                        logger.warning("No cookies received after login - this will cause download failures")
                    self.logged_in = True
                    return True
                else:
                    logger.error(f"AudiobookBay login failed with status {response.status}")
                    self.logged_in = False
                    return False
                        
        except asyncio.TimeoutError:
            logger.error(f"AudiobookBay login timed out after {self.timeout}s")
            self.logged_in = False
            return False
        except Exception as e:
            logger.error(f"AudiobookBay login error: {type(e).__name__}: {e}")
            self.logged_in = False
            return False
    
    def is_logged_in(self) -> bool:
        """Check if currently logged in"""
        return self.logged_in

# Singleton instance
audiobookbay_client = AudiobookBayClient()
