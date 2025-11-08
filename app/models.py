from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import json
from typing import List, Optional

Base = declarative_base()

class SearchResult(Base):
    __tablename__ = "search_results"
    
    id = Column(Integer, primary_key=True)
    query = Column(String, nullable=False)
    title = Column(String, nullable=False)
    author = Column(String)
    narrator = Column(String)
    size = Column(Integer)  # Size in bytes
    seeders = Column(Integer)
    leechers = Column(Integer)
    download_url = Column(Text)
    magnet_url = Column(Text)
    indexer = Column(String)
    quality = Column(String)
    format = Column(String)
    languages = Column(Text)  # Store as JSON string instead of JSON type
    score = Column(Float)
    age_days = Column(Float)
    created_at = Column(DateTime, default=func.now())
    
    def get_languages(self) -> List[str]:
        """Get languages as list from JSON string"""
        if not self.languages:
            return []
        try:
            return json.loads(self.languages)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_languages(self, languages: List[str]):
        """Set languages as JSON string"""
        if languages is None:
            self.languages = None
        else:
            self.languages = json.dumps(languages)

class DownloadJob(Base):
    __tablename__ = "download_jobs"
    
    id = Column(Integer, primary_key=True)
    search_result_id = Column(Integer, nullable=False)
    torrent_hash = Column(String)
    status = Column(String, default="pending")  # pending, starting, downloading, completed, failed, cancelled
    progress = Column(Float, default=0.0)
    download_path = Column(String)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    error_message = Column(Text)

def update_database_schema():
    """Update database schema - this will handle the migration"""
    from .database import engine
    Base.metadata.create_all(bind=engine)
