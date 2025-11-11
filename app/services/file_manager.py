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
            metadata['title'] = by_match.group(1).strip()  # Fixed: by_match instead of match
            metadata['author'] = by_match.group(2).strip()  # Fixed: by_match instead of match
            return metadata
        
        # Try bracket pattern
        bracket_match = re.search(r'^(.*?)\s*\[(.*)\]$', name)
        if bracket_match:
            metadata['title'] = bracket_match.group(1).strip()
            metadata['author'] = bracket_match.group(2).strip()
            return metadata
        
        # Try dash pattern - look for a dash separator that likely separates author and title
        dash_pattern = r'^(.+?)\s*[-–—]{1,}\s*(.+)$'
        dash_match = re.search(dash_pattern, name)
        if dash_match:
            author_candidate = dash_match.group(1).strip()
            title_candidate = dash_match.group(2).strip()
            
            # Basic validation: both parts should have reasonable length
            if len(author_candidate) > 2 and len(title_candidate) > 2:
                metadata['author'] = author_candidate
                metadata['title'] = title_candidate
                return metadata
        
        # Clean up any trailing dots or spaces - do this more thoroughly
        metadata['author'] = metadata['author'].strip().strip('.')
        metadata['title'] = metadata['title'].strip().strip('.')
        
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
        Organize a downloaded audiobook from qBittorrent location to library location
        
        Returns: Metadata about the organized audiobook
        """
        try:
            logger.info(f"Attempting to organize audiobook from path: {download_path}")
            
            if not download_path:
                logger.error("Download path is empty or None")
                return None
            
            if not os.path.exists(download_path):
                logger.error(f"Download path does not exist: {download_path}")
                # Try to list parent directory to help debug
                parent_dir = os.path.dirname(download_path)
                if os.path.exists(parent_dir):
                    logger.info(f"Parent directory exists: {parent_dir}")
                    try:
                        contents = os.listdir(parent_dir)
                        logger.info(f"Parent directory contains: {contents[:10]}")  # First 10 items
                    except Exception as e:
                        logger.error(f"Could not list parent directory: {e}")
                else:
                    logger.error(f"Parent directory does not exist: {parent_dir}")
                return None
            
            # If it's a file, get its directory
            if os.path.isfile(download_path):
                download_dir = os.path.dirname(download_path)
                is_single_file = True
                logger.info(f"Single file download: {download_path}")
            else:
                download_dir = download_path
                is_single_file = False
                logger.info(f"Directory download: {download_path}")
            
            # Get audio files to determine if this is an audiobook
            audio_files = self.get_audio_files(download_dir)
            if not audio_files:
                logger.warning(f"No audio files found in {download_dir}")
                return None
            
            # Extract metadata from the folder name or first audio file
            folder_name = os.path.basename(download_dir.rstrip('/'))
            metadata = self.extract_metadata_from_filename(folder_name)
            
            # If single file, try to extract better metadata from filename
            if is_single_file:
                file_metadata = self.extract_metadata_from_filename(os.path.basename(download_path))
                if file_metadata['author'] != 'Unknown Author':
                    metadata = file_metadata
            
            # Create safe folder names
            safe_author = self._make_filesystem_safe(metadata['author'])
            safe_title = self._make_filesystem_safe(metadata['title'])
            
            # Create library path: Library/Author/Title/
            author_dir = os.path.join(self.library_path, safe_author)
            title_dir = os.path.join(author_dir, safe_title)
            
            os.makedirs(title_dir, exist_ok=True)
            
            # Copy all files (not just audio) to preserve metadata, covers, etc.
            copied_files = []
            if is_single_file:
                # Single file download
                filename = os.path.basename(download_path)
                dest_path = os.path.join(title_dir, filename)
                if not os.path.exists(dest_path):
                    shutil.copy2(download_path, dest_path)
                    copied_files.append(filename)
                    logger.debug(f"Copied {filename} to library")
            else:
                # Directory download - copy all files
                for root, dirs, files in os.walk(download_dir):
                    for file in files:
                        src_path = os.path.join(root, file)
                        # Calculate relative path for nested directories
                        rel_path = os.path.relpath(src_path, download_dir)
                        dest_path = os.path.join(title_dir, rel_path)
                        
                        # Create subdirectories if needed
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        
                        if not os.path.exists(dest_path):
                            shutil.copy2(src_path, dest_path)
                            copied_files.append(rel_path)
                            logger.debug(f"Copied {rel_path} to library")
            
            logger.info(f"Organized audiobook: {metadata['title']} by {metadata['author']}")
            
            return {
                'author': metadata['author'],
                'title': metadata['title'],
                'library_path': title_dir,
                'author_path': author_dir,
                'files_copied': copied_files,
                'source_path': download_path
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
        """Clean up downloaded files from qBittorrent location after organization"""
        try:
            if os.path.exists(download_path):
                # Only delete if the file/folder is in our download path (safety check)
                if download_path.startswith(self.download_path):
                    if os.path.isfile(download_path):
                        os.remove(download_path)
                        logger.info(f"Deleted downloaded file: {download_path}")
                    else:
                        shutil.rmtree(download_path)
                        logger.info(f"Deleted downloaded folder: {download_path}")
                else:
                    logger.warning(f"Not deleting {download_path} - outside download directory")
        except Exception as e:
            logger.error(f"Failed to cleanup {download_path}: {e}")
    
    async def monitor_downloads_folder(self):
        """Monitor downloads folder for new audiobooks"""
        # This could be implemented with watchdog for real-time monitoring
        # For now, we'll process completed downloads on demand
        pass