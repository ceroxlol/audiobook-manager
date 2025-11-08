import pytest
import sys
import os

sys.path.append('/opt/audiobook-manager')

def test_config_loading():
    """Test that configuration loads correctly"""
    from app.config import config
    
    assert config.get('app.name') == 'Audiobook Manager'
    assert config.get('server.port') == 8000
    assert config.get('server.host') == '0.0.0.0'

def test_database_connection():
    """Test database connection and schema"""
    from app.database import engine, init_db
    from app.models import SearchResult, DownloadJob
    
    # This should not raise an exception
    init_db()
    
    # Test that tables exist
    assert SearchResult.__tablename__ in Base.metadata.tables
    assert DownloadJob.__tablename__ in Base.metadata.tables

def test_fastapi_app_creation():
    """Test that FastAPI app creates successfully"""
    from app.main import app
    
    assert app.title == 'Audiobook Manager'
    assert app.version == '1.0.0'
    assert '/api/v1/search' in [route.path for route in app.routes]

def test_static_files():
    """Test that static files are accessible"""
    import os
    assert os.path.exists('/opt/audiobook-manager/app/static/index.html')