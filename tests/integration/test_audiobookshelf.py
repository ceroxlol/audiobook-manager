import pytest
import sys
import asyncio
from unittest.mock import Mock, patch

sys.path.append('/opt/audiobook-manager')

@pytest.mark.asyncio
async def test_audiobookshelf_client_initialization():
    """Test Audiobookshelf client initialization"""
    from app.services.audiobookshelf import AudiobookshelfClient
    
    client = AudiobookshelfClient()
    assert client.base_url is not None
    assert client.api_key is not None

@pytest.mark.asyncio
async def test_file_manager_initialization():
    """Test file manager initialization"""
    from app.services.file_manager import FileManager
    
    manager = FileManager()
    assert manager.download_path is not None
    assert manager.library_path is not None

@pytest.mark.asyncio
async def test_metadata_extraction():
    """Test metadata extraction from filenames"""
    from app.services.file_manager import FileManager
    
    manager = FileManager()
    
    test_cases = [
        ("Author Name - Book Title.m4b", "Author Name", "Book Title"),
        ("Book Title by Author Name.mp3", "Author Name", "Book Title"),
        ("Author.Name.-.Book.Title.flac", "Author.Name", "Book.Title"),
    ]
    
    for filename, expected_author, expected_title in test_cases:
        metadata = manager.extract_metadata_from_filename(filename)
        assert metadata['author'] == expected_author
        assert metadata['title'] == expected_title

@pytest.mark.asyncio
async def test_download_manager_audiobookshelf_integration():
    """Test download manager integration with Audiobookshelf"""
    from app.services.download_manager import DownloadManager
    from app.models import SearchResult, DownloadJob
    from sqlalchemy.orm import Session
    
    manager = DownloadManager()
    
    # Mock the file organization
    with patch.object(manager.file_manager, 'organize_downloaded_audiobook') as mock_organize:
        mock_organize.return_value = {
            'author': 'Test Author',
            'title': 'Test Book',
            'library_path': '/library/Test Author/Test Book'
        }
        
        # Mock Audiobookshelf integration
        with patch.object(manager, '_add_to_audiobookshelf') as mock_abs:
            mock_abs.return_value = True
            
            # Test that the integration is called
            download_job = Mock(spec=DownloadJob)
            search_result = Mock(spec=SearchResult)
            search_result.title = 'Test Book'
            
            await manager._process_completed_download(download_job, search_result, Mock())
            
            mock_organize.assert_called_once()
            mock_abs.assert_called_once()