import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from .prowlarr import prowlarr_client
from .audiobookbay import audiobookbay_client
from ..models import SearchResult
from ..database import get_db

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.prowlarr = prowlarr_client
        self.audiobookbay = audiobookbay_client
    
    async def search_audiobooks(self, 
                               query: str, 
                               db: Session,
                               sources: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search for audiobooks from multiple sources and store results in database
        
        Args:
            query: Search query
            db: Database session
            sources: List of sources to search. Options: ["prowlarr", "audiobookbay"]
                    If None, searches all available sources
        """
        if sources is None:
            sources = ["prowlarr", "audiobookbay"]
        
        logger.info(f"Searching for audiobooks: {query} (sources: {', '.join(sources)})")
        
        # Run searches in parallel
        search_tasks = []
        
        if "prowlarr" in sources:
            search_tasks.append(self._search_prowlarr(query))
        
        if "audiobookbay" in sources:
            search_tasks.append(self._search_audiobookbay(query))
        
        # Execute all searches concurrently
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Merge results from all sources
        all_results = []
        for i, result in enumerate(search_results):
            if isinstance(result, Exception):
                logger.error(f"Search task {i} failed: {result}")
                continue
            if result:
                all_results.extend(result)
        
        logger.info(f"Total results from all sources: {len(all_results)}")
        
        # Store results in database
        db_results = []
        for result in all_results:
            db_result = SearchResult(
                query=query,
                title=result['title'],
                author=result['author'],
                narrator=result['narrator'],
                size=result['size'],
                seeders=result['seeders'],
                leechers=result['leechers'],
                download_url=result['download_url'],
                magnet_url=result['magnet_url'],
                indexer=result['indexer'],
                source=result.get('source', 'prowlarr'),  # Store the source
                quality=result['quality'],
                format=result['format'],
                score=result['score'],
                age_days=result['age']
            )
            # Use the set_languages method
            db_result.set_languages(result['languages'])
            
            db.add(db_result)
            db_results.append(db_result)
        
        db.commit()
        
        # Convert to API response format
        api_results = []
        for result in db_results:
            api_result = {
                'id': result.id,
                'title': result.title,
                'author': result.author,
                'narrator': result.narrator,
                'size': result.size,
                'seeders': result.seeders,
                'leechers': result.leechers,
                'quality': result.quality,
                'format': result.format,
                'languages': result.get_languages(),
                'indexer': result.indexer,
                'source': result.source,  # Include source in response
                'score': result.score,
                'age_days': result.age_days
            }
            api_results.append(api_result)
        
        # Sort by score (highest first)
        api_results.sort(key=lambda x: x['score'], reverse=True)
        
        return api_results
    
    async def _search_prowlarr(self, query: str) -> List[Dict[str, Any]]:
        """Search via Prowlarr"""
        try:
            results = await self.prowlarr.search(query)
            # Add source identifier to each result
            for result in results:
                result['source'] = 'prowlarr'
            logger.info(f"Prowlarr returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Prowlarr search failed: {e}")
            return []
    
    async def _search_audiobookbay(self, query: str) -> List[Dict[str, Any]]:
        """Search via AudiobookBay"""
        try:
            results = await self.audiobookbay.search(query)
            # Add source identifier to each result
            for result in results:
                result['source'] = 'audiobookbay'
            logger.info(f"AudiobookBay returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"AudiobookBay search failed: {e}")
            return []
    
    async def get_recent_searches(self, db: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search queries"""
        from sqlalchemy import desc
        
        recent = db.query(SearchResult.query).distinct().order_by(
            desc(SearchResult.created_at)
        ).limit(limit).all()
        
        return [item[0] for item in recent]

# Singleton instance
search_service = SearchService()
