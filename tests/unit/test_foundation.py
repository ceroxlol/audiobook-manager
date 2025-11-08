import pytest
import sys
import os

# Add the app directory to Python path
sys.path.append('/opt/audiobook-manager')

def test_config_loading():
    """Test that configuration loads correctly"""
    from app.config import config
    
    # Test that basic config values exist
    assert config.get('app.name') is not None
    assert config.get('server.port') is not None
    assert config.get('server.host') is not None
    
    # Test that we can access nested values
    integrations = config.get('integrations')
    assert integrations is not None

def test_database_connection():
    """Test database connection and schema"""
    from app.database import engine, init_db
    from app.models import Base, SearchResult, DownloadJob
    
    try:
        # Initialize database (this should not raise an exception)
        init_db()
        
        # Test that tables can be accessed
        assert hasattr(SearchResult, '__tablename__')
        assert hasattr(DownloadJob, '__tablename__')
        
        # Test that we can create a session
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        session.close()
        
    except Exception as e:
        pytest.fail(f"Database test failed: {e}")

def test_fastapi_app_creation():
    """Test that FastAPI app creates successfully"""
    from app.main import app
    
    assert app.title == 'Audiobook Manager'
    assert hasattr(app, 'version')
    
    # Check that our API routes exist
    routes = [route.path for route in app.routes]
    assert any('/api/v1/search' in route for route in routes)
    assert any('/api/v1/queue' in route for route in routes)

def test_static_files():
    """Test that static files are accessible"""
    static_files_exist = os.path.exists('/opt/audiobook-manager/app/static/index.html')
    assert static_files_exist, "Static files directory should exist"