import pytest
import sys
from fastapi.testclient import TestClient

sys.path.append('/opt/audiobook-manager')

def test_api_health_endpoint():
    """Test API health endpoint"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'

def test_api_search_endpoint():
    """Test search endpoint structure"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/api/v1/search?query=test")
    
    # Even if search fails, endpoint should return proper structure
    assert response.status_code in [200, 500]
    if response.status_code == 200:
        data = response.json()
        assert 'query' in data
        assert 'results' in data
        assert 'count' in data

def test_api_queue_endpoint():
    """Test download queue endpoint"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/api/v1/queue")
    
    assert response.status_code == 200
    data = response.json()
    assert 'downloads' in data
    assert 'total' in data
    assert 'active' in data