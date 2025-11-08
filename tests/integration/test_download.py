import pytest
import sys
import asyncio
from unittest.mock import Mock, patch, AsyncMock

sys.path.append('/opt/audiobook-manager')

@pytest.mark.asyncio
async def test_qbittorrent_client_initialization():
    """Test qBittorrent client initialization"""
    from app.services.qbittorrent import QBittorrentClient
    
    client = QBittorrentClient()
    assert client.base_url is not None
    assert client.username is not None

@pytest.mark.asyncio
async def test_download_manager_initialization():
    """Test download manager initialization"""
    from app.services.download_manager import DownloadManager
    
    manager = DownloadManager()
    assert hasattr(manager, 'active_downloads')
    assert hasattr(manager, 'monitoring_tasks')
    assert hasattr(manager, 'file_manager')

@pytest.mark.asyncio
async def test_torrent_addition_logic():
    """Test torrent addition logic"""
    from app.services.download_manager import DownloadManager
    from app.models import SearchResult, DownloadJob
    
    manager = DownloadManager()
    
    # Mock search result
    mock_search_result = Mock(spec=SearchResult)
    mock_search_result.id = 1
    mock_search_result.title = 'Test Book'
    mock_search_result.magnet_url = 'magnet:?xt=urn:btih:test'
    
    # Mock database session
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_search_result
    mock_db.add = Mock()
    mock_db.commit = Mock()
    
    # Mock qBittorrent client methods
    with patch('app.services.download_manager.qbittorrent_client') as mock_qbt:
        mock_qbt.ensure_audiobooks_category = AsyncMock(return_value=True)
        mock_qbt.add_torrent = AsyncMock(return_value=True)
        
        result = await manager.start_download(1, mock_db)
        
        assert result is not None
        assert result.search_result_id == 1
        mock_qbt.add_torrent.assert_called_once()

@pytest.mark.asyncio
async def test_download_monitoring_logic():
    """Test download monitoring logic"""
    from app.services.download_manager import DownloadManager
    
    manager = DownloadManager()
    
    # Mock the monitoring method
    with patch.object(manager, '_start_monitoring', new_callable=AsyncMock) as mock_monitor:
        # Mock search result and database
        mock_search_result = Mock()
        mock_search_result.id = 1
        mock_search_result.title = 'Test Book'
        mock_search_result.magnet_url = 'magnet:test'
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_search_result
        mock_db.add = Mock()
        mock_db.commit = Mock()
        
        # Mock qBittorrent
        with patch('app.services.download_manager.qbittorrent_client') as mock_qbt:
            mock_qbt.ensure_audiobooks_category = AsyncMock(return_value=True)
            mock_qbt.add_torrent = AsyncMock(return_value=True)
            
            result = await manager.start_download(1, mock_db)
            
            # Check that monitoring was started
            mock_monitor.assert_called_once_with(result.id, mock_db)