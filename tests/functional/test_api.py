import pytest
import sys
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock

sys.path.append('/opt/audiobook-manager')

def test_api_health_endpoint():
    """Test API health endpoint"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert 'status' in data
    assert 'service' in data

def test_api_search_endpoint():
    """Test search endpoint structure"""
    from app.main import app
    
    client = TestClient(app)
    
    # Mock the search service to avoid external dependencies
    with patch('app.api.endpoints.search_service') as mock_search:
        mock_search.search_audiobooks = AsyncMock(return_value=[])
        
        response = client.get("/api/v1/search?query=test")
        
        # Endpoint should return proper structure even with mocked data
        assert response.status_code == 200
        data = response.json()
        assert 'query' in data
        assert 'results' in data
        assert 'count' in data

def test_api_queue_endpoint():
    """Test download queue endpoint"""
    from app.main import app
    
    client = TestClient(app)
    
    # Mock database session
    with patch('app.api.endpoints.get_db') as mock_db:
        mock_session = Mock()
        mock_session.query.return_value.order_by.return_value.all.return_value = []
        mock_db.return_value = mock_session
        
        response = client.get("/api/v1/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert 'downloads' in data
        assert 'total' in data
        assert 'active' in data

def test_api_status_endpoint():
    """Test status endpoint"""
    from app.main import app
    
    client = TestClient(app)
    
    # Mock the integration clients
    with patch('app.api.endpoints.prowlarr_client') as mock_prowlarr, \
         patch('app.api.endpoints.qbittorrent_client') as mock_qbt, \
         patch('app.api.endpoints.audiobookshelf_client') as mock_abs:
        
        mock_prowlarr.test_connection = AsyncMock(return_value=True)
        mock_qbt.test_connection = AsyncMock(return_value=True)
        mock_qbt.get_download_speed = AsyncMock(return_value=0)
        mock_abs.test_connection = AsyncMock(return_value=True)
        mock_abs.get_libraries = AsyncMock(return_value=[])
        
        response = client.get("/api/v1/status")
        
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        assert 'integrations' in data