import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote
import logging
from ..config import config

logger = logging.getLogger(__name__)

class ProwlarrClient:
    def __init__(self):
        self.base_url = f"http://{config.get('integrations.prowlarr.host')}:{config.get('integrations.prowlarr.port')}"
        self.api_key = config.get('integrations.prowlarr.api_key')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make API request to Prowlarr"""
        if not self.session:
            async with aiohttp.ClientSession() as session:
                return await self._make_request_with_session(session, endpoint, params)
        else:
            return await self._make_request_with_session(self.session, endpoint, params)
    
    async def _make_request_with_session(self, session: aiohttp.ClientSession, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make request with existing session"""
        url = None
        try:
            url = f"{self.base_url}/api/v1/{endpoint}"
            default_params = {'apikey': self.api_key}
            if params:
                default_params.update(params)
            
            logger.debug(f"Making Prowlarr request to: {url}")
            
            async with session.get(url, params=default_params, timeout=30) as response:
                if response.status == 200:
                    logger.debug(f"Prowlarr request successful: {url}")
                    return await response.json()
                else:
                    # Get response body for error details
                    response_text = await response.text()
                    logger.error(
                        f"Prowlarr API error: HTTP {response.status} at {url}\n"
                        f"Response: {response_text[:500]}"  # Limit response text
                    )
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Prowlarr request timed out after 30s: {url}")
            return None
        except aiohttp.ClientConnectorError as e:
            logger.error(
                f"Prowlarr connection error at {url}: Cannot connect to {self.base_url}\n"
                f"Error: {type(e).__name__}: {e}"
            )
            return None
        except aiohttp.ClientError as e:
            logger.error(
                f"Prowlarr client error at {url}: {type(e).__name__}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error making request to Prowlarr at {url}: {type(e).__name__}: {e}",
                exc_info=True  # Include full traceback
            )
            return None
    
    async def search(self, query: str, categories: List[int] = None) -> List[Dict[str, Any]]:
        """
        Search for content via Prowlarr
        
        Args:
            query: Search query
            categories: List of category IDs (3030 for Audiobooks, 3035 for Audio)
        """
        if categories is None:
            categories = [3030, 3035]  # Audiobook categories
        
        params = {
            'query': query,
            'categories': categories,
            'type': 'search'
        }
        
        logger.info(f"Searching Prowlarr for: '{query}' (categories: {categories})")
        
        try:
            results = await self._make_request('search', params)
            if not results:
                logger.warning(f"No results from Prowlarr for query: '{query}'")
                return []
            
            logger.debug(f"Prowlarr returned {len(results)} raw results for: '{query}'")
            filtered = await self._filter_and_rank_results(results)
            logger.info(f"Prowlarr returned {len(filtered)} filtered results for: '{query}'")
            
            return filtered
        except Exception as e:
            logger.error(
                f"Prowlarr search failed for query '{query}': {type(e).__name__}: {e}",
                exc_info=True
            )
            return []
    
    async def _filter_and_rank_results(self, results: List[Dict]) -> List[Dict]:
        """Filter and rank search results for audiobooks"""
        filtered_results = []
        
        for result in results:
            # Skip non-audiobook results
            if not self._is_audiobook_result(result):
                continue
            
            # Calculate score for ranking
            score = self._calculate_result_score(result)
            
            filtered_results.append({
                'id': result.get('guid'),
                'title': result.get('title', ''),
                'author': self._extract_author(result),
                'narrator': self._extract_narrator(result),
                'size': result.get('size', 0),
                'seeders': result.get('seeders', 0),
                'leechers': result.get('leechers', 0),
                'download_url': result.get('downloadUrl', ''),
                'magnet_url': result.get('magnetUrl', ''),
                'indexer': result.get('indexer', ''),
                'quality': self._extract_quality(result),
                'format': self._extract_format(result),
                'score': score,
                'age': result.get('ageHours', 0) / 24,  # Convert to days
                'languages': self._extract_languages(result)
            })
        
        # Sort by score (highest first)
        filtered_results.sort(key=lambda x: x['score'], reverse=True)
        return filtered_results
    
    def _is_audiobook_result(self, result: Dict) -> bool:
        """Check if result is likely an audiobook"""
        title = result.get('title', '').lower()
        categories = result.get('categories', [])
        
        # Check categories
        audiobook_categories = [3030, 3035]  # Audiobook categories in Prowlarr
        if any(cat in audiobook_categories for cat in categories):
            return True
        
        # Check title for audiobook indicators
        audiobook_keywords = [
            'audiobook', 'audio book', 'm4b', 'm4a', 'mp3', 'flac', 
            'read by', 'narrated', 'narration', 'audible'
        ]
        
        if any(keyword in title for keyword in audiobook_keywords):
            return True
        
        # Check for common audiobook file extensions in title
        audio_extensions = ['.m4b', '.m4a', '.mp3', '.flac', '.aac']
        if any(ext in title for ext in audio_extensions):
            return True
        
        return False
    
    def _calculate_result_score(self, result: Dict) -> float:
        """Calculate a score for ranking results"""
        score = 0.0
        
        # Seeders are very important
        seeders = result.get('seeders', 0)
        if seeders > 50:
            score += 30
        elif seeders > 20:
            score += 20
        elif seeders > 5:
            score += 10
        elif seeders > 0:
            score += 5
        
        # Leechers negatively affect score
        leechers = result.get('leechers', 0)
        if leechers > seeders:
            score -= 10
        
        # Size matters - prefer complete audiobooks
        size = result.get('size', 0)
        if 50 * 1024 * 1024 < size < 500 * 1024 * 1024:  # 50MB - 500MB range
            score += 15
        elif 500 * 1024 * 1024 < size < 2 * 1024 * 1024 * 1024:  # 500MB - 2GB range
            score += 25  # Full audiobooks are usually in this range
        elif size > 2 * 1024 * 1024 * 1024:  # Over 2GB
            score += 5   # Might be a collection
        
        # Prefer newer content
        age_days = result.get('ageHours', 0) / 24
        if age_days < 7:  # Less than a week old
            score += 10
        elif age_days < 30:  # Less than a month old
            score += 5
        
        # Quality preferences
        title = result.get('title', '').lower()
        if 'm4b' in title:
            score += 20  # Prefer M4B format
        elif 'flac' in title:
            score += 15  # High quality
        elif 'mp3' in title:
            score += 10
        
        # Trusted indexers get bonus
        indexer = result.get('indexer', '').lower()
        trusted_indexers = ['mam', 'myanonamouse', 'abtorrents', 'audiobookbay']
        if any(trusted in indexer for trusted in trusted_indexers):
            score += 15
        
        return score
    
    def _extract_author(self, result: Dict) -> str:
        """Extract author name from result"""
        title = result.get('title', '')
        
        # Common patterns in audiobook titles
        patterns = [
            ' by ', ' - ', ' – ', ' — '
        ]
        
        for pattern in patterns:
            if pattern in title:
                # Try to extract author from before common separators
                parts = title.split(pattern)
                if len(parts) > 1:
                    # Author is often in the first part
                    author_candidate = parts[0].strip()
                    if len(author_candidate) < 50:  # Reasonable author name length
                        return author_candidate
        
        return "Unknown Author"
    
    def _extract_narrator(self, result: Dict) -> str:
        """Extract narrator name from result"""
        title = result.get('title', '').lower()
        description = result.get('description', '').lower()
        
        # Look for narrator indicators
        narrator_indicators = ['narrated by', 'read by', 'narration by', 'narrator:']
        
        for indicator in narrator_indicators:
            if indicator in title:
                start_idx = title.find(indicator) + len(indicator)
                # Extract narrator name (assume it's the next words until common separators)
                remaining = title[start_idx:]
                for sep in [' - ', ' – ', ' — ', ' [', ' (', '.']:
                    if sep in remaining:
                        narrator = remaining.split(sep)[0].strip()
                        if narrator:
                            return narrator.title()
        
        return "Unknown Narrator"
    
    def _extract_quality(self, result: Dict) -> str:
        """Extract quality information"""
        title = result.get('title', '').lower()
        
        if '320kbps' in title or '320kb' in title:
            return '320kbps'
        elif '256kbps' in title or '256kb' in title:
            return '256kbps'
        elif '128kbps' in title or '128kb' in title:
            return '128kbps'
        elif 'flac' in title or 'lossless' in title:
            return 'FLAC'
        elif 'm4b' in title:
            return 'M4B'
        else:
            return 'Unknown'
    
    def _extract_format(self, result: Dict) -> str:
        """Extract file format"""
        title = result.get('title', '').lower()
        
        if 'm4b' in title:
            return 'M4B'
        elif 'mp3' in title:
            return 'MP3'
        elif 'flac' in title:
            return 'FLAC'
        elif 'm4a' in title:
            return 'M4A'
        else:
            return 'Unknown'
    
    def _extract_languages(self, result: Dict) -> List[str]:
        """Extract languages from result"""
        title = result.get('title', '').lower()
        languages = []
        
        language_keywords = {
            'english': ['english', 'eng'],
            'german': ['german', 'deutsch', 'ger'],
            'french': ['french', 'français', 'fr'],
            'spanish': ['spanish', 'español', 'sp'],
        }
        
        for lang, keywords in language_keywords.items():
            if any(keyword in title for keyword in keywords):
                languages.append(lang)
        
        return languages if languages else ['Unknown']
    
    async def test_connection(self) -> bool:
        """Test connection to Prowlarr"""
        try:
            logger.debug(f"Testing connection to Prowlarr at {self.base_url}")
            result = await self._make_request('system/status')
            
            if result is not None:
                logger.info(f"Prowlarr connection test successful: {self.base_url}")
                return True
            else:
                logger.warning(f"Prowlarr connection test failed: no valid response from {self.base_url}")
                return False
        except Exception as e:
            logger.error(
                f"Prowlarr connection test failed for {self.base_url}: {type(e).__name__}: {e}",
                exc_info=True
            )
            return False

# Singleton instance
prowlarr_client = ProwlarrClient()
