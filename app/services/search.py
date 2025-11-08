import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import logging

from .prowlarr import prowlarr_client
from ..models import SearchResult
from ..database import get_db

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.prowlarr = prowlarr_client
    
    async def search_audiobooks(self, query: str, db: Session) -> List[Dict[str, Any]]:
        """
        Search for audiobooks and store results in database
        """
        logger.info(f"Searching for audiobooks: {query}")
        
        # Search via Prowlarr
        results = await self.prowlarr.search(query)
        
        # Store results in database
        db_results = []
        for result in results:
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
                'languages': result.get_languages(),  # Use get_languages method
                'indexer': result.indexer,
                'score': result.score,
                'age_days': result.age_days
            }
            api_results.append(api_result)
        
        return api_results
    
    async def get_recent_searches(self, db: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search queries"""
        from sqlalchemy import desc
        
        recent = db.query(SearchResult.query).distinct().order_by(
            desc(SearchResult.created_at)
        ).limit(limit).all()
        
        return [item[0] for item in recent]

# Singleton instance
search_service = SearchService()
