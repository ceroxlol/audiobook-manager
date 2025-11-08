import os
import shutil
import asyncio
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import re

from ..config import config

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self):
        self.download_path = config.get('storage.download_path')
        self.library_path = config.get('storage.library_path')
        
        # Ensure directories exist
        os.makedirs(self.download_path, exist_ok=True)
        os.makedirs(self.library_path, exist_ok=True)
    
    def extract_metadata_from_filename(self, filename: str) -> Dict[str, str]:
        """Extract author and title from filename"""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        
        metadata = {'author': 'Unknown Author', 'title': name}
        
        # Try "Title by Author" pattern first (most specific)
        by_match = re.search(r'^(.*?)\s+by\s+(.*)$', name, re.IGNORECASE)
        if by_match:
            metadata['title'] = by_match.group(1).strip()
            metadata['author'] = by_match.group(2).strip()
            return metadata
        
        # Try bracket pattern
        bracket_match = re.search(r'^(.*?)\s*\[(.*)\]$', name)
        if bracket_match:
            metadata['title'] = bracket_match.group(1).strip()
            metadata['author'] = bracket_match.group(2).strip()
            return metadata
        
        # Try dash pattern - look for a dash separator that likely separates author and title
        # This pattern tries to find a dash that has reasonable content on both sides
        dash_pattern = r'^(.+?)\s*[-–—]{1,}\s*(.+)$'
        dash_match = re.search(dash_pattern, name)
        if dash_match:
            author_candidate = dash_match.group(1).strip()
            title_candidate = dash_match.group(2).strip()
            
            # If author candidate contains dashes, try to find the last dash as separator
            if '-' in author_candidate and not title_candidate.startswith('-'):
                # Split on dashes and try different combinations
                parts = author_candidate.split('-')
                # Try using the last dash as separator
                if len(parts) > 1:
                    author = '-'.join(parts[:-1]).strip()
                    title = parts[-1].strip() + ' ' + title_candidate
                    if len(author) > 2 and len(title) > 2:
                        metadata['author'] = author
                        metadata['title'] = title
                        return metadata
            
            # Basic validation: both parts should have reasonable length
            if len(author_candidate) > 2 and len(title_candidate) > 2:
                metadata['author'] = author_candidate
                metadata['title'] = title_candidate
                return metadata
        
        # Clean up any trailing dots or spaces
        metadata['author'] = metadata['author'].strip('. ')
        metadata['title'] = metadata['title'].strip('. ')
        
        return metadata
    
    def get_audio_files(self, directory: str) -> List[str]:
        """Get all audio files in a directory"""
        audio_extensions = {'.mp3', '.m4b', '.m4a', '.flac', '.aac', '.ogg', '.wav'}
        audio_files = []
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if Path(file).suffix.lower() in audio_extensions:
                    audio_files.append(os.path.join(root, file))
        
        return audio_files
    
    def is_audiobook_directory(self, directory: str) -> bool:
        """Check if a directory contains audiobook files"""
        audio_files = self.get_audio_files(directory)
        return len(audio_files) > 0
    
    async def organize_downloaded_audiobook(self, download_path: str) -> Optional[Dict[str, Any]]:
        """
        Organize a downloaded audiobook into the library structure
        
        Returns: Metadata about the organized audiobook
        """
        try:
            if not os.path.exists(download_path):
                logger.error(f"Download path does not exist: {download_path}")
                return None
            
            # If it's a file, get its directory
            if os.path.isfile(download_path):
                download_dir = os.path.dirname(download_path)
            else:
                download_dir = download_path
            
            # Get audio files to determine if this is an audiobook
            audio_files = self.get_audio_files(download_dir)
            if not audio_files:
                logger.warning(f"No audio files found in {download_dir}")
                return None
            
            # Extract metadata from the first audio file
            first_file = audio_files[0]
            filename = os.path.basename(first_file)
            metadata = self.extract_metadata_from_filename(filename)
            
            # Create safe folder names
            safe_author = self._make_filesystem_safe(metadata['author'])
            safe_title = self._make_filesystem_safe(metadata['title'])
            
            # Create library path: Library/Author/Title/
            author_dir = os.path.join(self.library_path, safe_author)
            title_dir = os.path.join(author_dir, safe_title)
            
            os.makedirs(title_dir, exist_ok=True)
            
            # Copy/Move files to library
            for audio_file in audio_files:
                filename = os.path.basename(audio_file)
                dest_path = os.path.join(title_dir, filename)
                
                if not os.path.exists(dest_path):
                    shutil.copy2(audio_file, dest_path)
                    logger.debug(f"Copied {filename} to library")
            
            logger.info(f"Organized audiobook: {metadata['title']} by {metadata['author']}")
            
            return {
                'author': metadata['author'],
                'title': metadata['title'],
                'library_path': title_dir,
                'author_path': author_dir,
                'audio_files': [os.path.basename(f) for f in audio_files]
            }
            
        except Exception as e:
            logger.error(f"Failed to organize audiobook {download_path}: {e}")
            return None
    
    def _make_filesystem_safe(self, name: str) -> str:
        """Make a string safe for filesystem use"""
        # Replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing spaces and dots
        safe_name = safe_name.strip('. ')
        # Limit length
        return safe_name[:100]
    
    async def cleanup_download(self, download_path: str):
        """Clean up downloaded files after organization"""
        try:
            if os.path.exists(download_path):
                if os.path.isfile(download_path):
                    os.remove(download_path)
                else:
                    shutil.rmtree(download_path)
                logger.info(f"Cleaned up download: {download_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup {download_path}: {e}")
    
    async def monitor_downloads_folder(self):
        """Monitor downloads folder for new audiobooks"""
        # This could be implemented with watchdog for real-time monitoring
        # For now, we'll process completed downloads on demand
        pass