import pytest
import sys
import asyncio
from unittest.mock import Mock, patch

sys.path.append('/opt/audiobook-manager')

@pytest.mark.asyncio
async def test_prowlarr_client_initialization():
    """Test Prowlarr client initialization"""
    from app.services.prowlarr import ProwlarrClient
    
    client = ProwlarrClient()
    assert client.base_url is not None
    assert client.api_key is not None

@pytest.mark.asyncio
async def test_search_result_filtering():
    """Test audiobook result filtering logic"""
    from app.services.prowlarr import ProwlarrClient
    
    client = ProwlarrClient()
    
    # Test data
    mock_result = {
        'title': 'Test Audiobook.m4b',
        'categories': [3030],  # Audiobook category
        'size': 100 * 1024 * 1024,  # 100MB
        'seeders': 10,
        'leechers': 2
    }
    
    # Test audiobook detection
    assert client._is_audiobook_result(mock_result) == True
    
    # Test non-audiobook
    non_audio_result = mock_result.copy()
    non_audio_result['categories'] = [2000]  # TV category
    non_audio_result['title'] = 'TV Show'
    assert client._is_audiobook_result(non_audio_result) == False

@pytest.mark.asyncio
async def test_search_service_integration():
    """Test search service integration"""
    from app.services.search import SearchService
    from app.models import SearchResult
    from sqlalchemy.orm import Session
    
    search_service = SearchService()
    
    # Mock the Prowlarr search to return test data
    with patch.object(search_service.prowlarr, 'search') as mock_search:
        mock_search.return_value = [{
            'title': 'Test Book',
            'author': 'Test Author',
            'narrator': 'Test Narrator',
            'size': 100000000,
            'seeders': 5,
            'leechers': 1,
            'download_url': 'http://example.com/torrent',
            'magnet_url': 'magnet:test',
            'indexer': 'test-indexer',
            'quality': '128kbps',
            'format': 'MP3',
            'languages': ['english'],
            'score': 85.5,
            'age': 2.5
        }]
        
        # Mock database session
        mock_db = Mock(spec=Session)
        mock_db.add = Mock()
        mock_db.commit = Mock()
        
        results = await search_service.search_audiobooks('test query', mock_db)
        
        assert len(results) == 1
        assert results[0]['title'] == 'Test Book'
        assert results[0]['author'] == 'Test Author'