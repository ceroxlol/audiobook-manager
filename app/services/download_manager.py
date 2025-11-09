import asyncio
import time
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import logging
import os

from .qbittorrent import qbittorrent_client
from .prowlarr import prowlarr_client
from .audiobookshelf import audiobookshelf_client
from .file_manager import FileManager
from ..models import DownloadJob, SearchResult
from ..database import get_db

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self):
        self.active_downloads: Dict[str, asyncio.Task] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.file_manager = FileManager()
    
    async def start_download(self, 
                           search_result_id: int, 
                           db: Session) -> Optional[DownloadJob]:
        """
        Start downloading a search result
        """
        # Get search result
        result = db.query(SearchResult).filter(SearchResult.id == search_result_id).first()
        if not result:
            logger.error(f"Search result {search_result_id} not found")
            return None
        
        # Create download job
        download_job = DownloadJob(
            search_result_id=search_result_id,
            status="starting"
        )
        db.add(download_job)
        db.commit()
        
        try:
            # Ensure audiobooks category exists
            await qbittorrent_client.ensure_audiobooks_category()
            
            # Get download URL (prefer magnet URL)
            download_url = result.magnet_url or result.download_url
            if not download_url:
                logger.error(f"No download URL for result {search_result_id}")
                download_job.status = "failed"
                download_job.error_message = "No download URL available"
                db.commit()
                return download_job
            
            # Add to qBittorrent
            success = await qbittorrent_client.add_torrent(
                torrent_url=download_url,
                category="audiobooks",
                tags=[f"audiobook-manager-{download_job.id}"]
            )
            
            if not success:
                download_job.status = "failed"
                download_job.error_message = "Failed to add torrent to qBittorrent"
                db.commit()
                return download_job
            
            download_job.status = "downloading"
            db.commit()
            
            logger.info(f"Started download for: {result.title} (Job: {download_job.id})")
            
            # Start monitoring this download
            await self._start_monitoring(download_job.id, db)
            
            return download_job
            
        except Exception as e:
            logger.error(f"Failed to start download {search_result_id}: {e}")
            download_job.status = "failed"
            download_job.error_message = str(e)
            db.commit()
            return download_job
    
    async def _start_monitoring(self, job_id: int, db: Session):
        """Start monitoring a download job"""
        if job_id in self.monitoring_tasks:
            return
        
        task = asyncio.create_task(self._monitor_download(job_id, db))
        self.monitoring_tasks[job_id] = task
    
    async def _monitor_download(self, job_id: int, db: Session):
        """Monitor download progress and handle completion"""
        logger.info(f"Started monitoring download job {job_id}")
        
        try:
            download_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if not download_job:
                logger.error(f"Download job {job_id} not found for monitoring")
                return
            
            search_result = db.query(SearchResult).filter(SearchResult.id == download_job.search_result_id).first()
            if not search_result:
                logger.error(f"Search result for job {job_id} not found")
                return
            
            # We'll check for the torrent by looking for our tag
            target_tag = f"audiobook-manager-{job_id}"
            max_attempts = 600  # 50 minutes (5 second intervals)
            attempts = 0
            
            while attempts < max_attempts:
                attempts += 1
                
                try:
                    # Get all torrents in audiobooks category
                    torrents = await qbittorrent_client.get_torrents(category="audiobooks")
                    
                    # Find our torrent (by name initially, since we don't have hash)
                    matching_torrents = [
                        t for t in torrents 
                        if search_result.title.lower() in t.get('name', '').lower()
                        or target_tag in t.get('tags', '')
                    ]
                    
                    if matching_torrents:
                        torrent = matching_torrents[0]
                        torrent_hash = torrent.get('hash')
                        
                        # Update job with torrent hash
                        if not download_job.torrent_hash:
                            download_job.torrent_hash = torrent_hash
                            db.commit()
                        
                        # Update progress
                        progress = torrent.get('progress', 0) * 100
                        download_job.progress = progress
                        
                        # Check status
                        state = torrent.get('state', '')
                        
                        if progress >= 100:
                            # Download completed - process the audiobook
                            download_path = torrent.get('content_path', '')
                            download_job.download_path = download_path
                            
                            await self._process_completed_download(download_job, search_result, db)
                            break
                            
                        elif state in ['error', 'missingFiles', 'pausedUP']:
                            download_job.status = "failed"
                            download_job.error_message = f"Torrent state: {state}"
                            db.commit()
                            logger.error(f"Download failed for job {job_id}: {state}")
                            break
                        else:
                            download_job.status = "downloading"
                            db.commit()
                    
                    else:
                        # Torrent not found yet, might need more time
                        if attempts > 60:  # After 5 minutes
                            download_job.status = "failed"
                            download_job.error_message = "Torrent not found in qBittorrent after timeout"
                            db.commit()
                            logger.error(f"Torrent not found for job {job_id}")
                            break
                
                except Exception as e:
                    logger.error(f"Error monitoring download job {job_id}: {e}")
                
                # Wait before next check
                await asyncio.sleep(5)
            
            # Cleanup monitoring task
            if job_id in self.monitoring_tasks:
                del self.monitoring_tasks[job_id]
                
        except Exception as e:
            logger.error(f"Monitoring task failed for job {job_id}: {e}")
            if job_id in self.monitoring_tasks:
                del self.monitoring_tasks[job_id]

    async def _process_completed_download(self, 
                                        download_job: DownloadJob, 
                                        search_result: SearchResult, 
                                        db: Session):
        """Process a completed download - organize and add to Audiobookshelf"""
        try:
            download_job.status = "processing"
            db.commit()
            
            logger.info(f"Processing completed download: {search_result.title}")
            
            # Organize the downloaded files
            organization_result = await self.file_manager.organize_downloaded_audiobook(
                download_job.download_path
            )
            
            if not organization_result:
                download_job.status = "failed"
                download_job.error_message = "Failed to organize downloaded files"
                db.commit()
                return
            
            # Add to Audiobookshelf
            abs_success = await self._add_to_audiobookshelf(organization_result, search_result)
            
            if abs_success:
                download_job.status = "completed"
                download_job.completed_at = time.time()
                logger.info(f"Successfully processed download: {search_result.title}")
                
                # Cleanup download files
                await self.file_manager.cleanup_download(download_job.download_path)
                
            else:
                download_job.status = "completed_with_warning"
                download_job.error_message = "Download completed but failed to add to Audiobookshelf"
                logger.warning(f"Download completed but Audiobookshelf integration failed: {search_result.title}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Failed to process completed download {download_job.id}: {e}")
            download_job.status = "failed"
            download_job.error_message = f"Processing failed: {str(e)}"
            db.commit()
    
    async def _add_to_audiobookshelf(self, 
                                   organization_result: Dict[str, Any], 
                                   search_result: SearchResult) -> bool:
        """Add organized audiobook to Audiobookshelf"""
        try:
            # Get libraries
            libraries = await audiobookshelf_client.get_libraries()
            if not libraries:
                logger.error("No libraries found in Audiobookshelf")
                return False
            
            # Use the first library (you might want to make this configurable)
            library = libraries[0]
            
            # Check if audiobook already exists
            existing = await audiobookshelf_client.find_audiobook_by_title(
                organization_result['title'],
                organization_result['author']
            )
            
            if existing:
                logger.info(f"Audiobook already exists in library: {organization_result['title']}")
                return True
            
            # Add to library
            result = await audiobookshelf_client.add_item_to_library(
                library_id=library['id'],
                folder_path=organization_result['library_path'],
                title=organization_result['title'],
                author=organization_result['author']
            )
            
            if result:
                # Trigger library scan
                await audiobookshelf_client.scan_library(library['id'])
                logger.info(f"Successfully added to Audiobookshelf: {organization_result['title']}")
                return True
            else:
                logger.error(f"Failed to add to Audiobookshelf: {organization_result['title']}")
                return False
                
        except Exception as e:
            logger.error(f"Audiobookshelf integration failed: {e}")
            return False
    
    async def get_download_status(self, job_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Get detailed download status"""
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return None
        
        result = db.query(SearchResult).filter(SearchResult.id == job.search_result_id).first()
        
        status = {
            'job_id': job.id,
            'status': job.status,
            'progress': job.progress,
            'title': result.title if result else 'Unknown',
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message
        }
        
        # If downloading, get more details from qBittorrent
        if job.status == "downloading" and job.torrent_hash:
            try:
                torrent = await qbittorrent_client.get_torrent(job.torrent_hash)
                if torrent:
                    status.update({
                        'download_speed': torrent.get('dlspeed', 0),
                        'upload_speed': torrent.get('upspeed', 0),
                        'size': torrent.get('size', 0),
                        'downloaded': torrent.get('downloaded', 0),
                        'eta': torrent.get('eta', 0),
                        'seeds': torrent.get('num_seeds', 0),
                        'peers': torrent.get('num_leechs', 0)
                    })
            except Exception as e:
                logger.error(f"Failed to get torrent details: {e}")
        
        return status
    
    async def cancel_download(self, job_id: int, db: Session, delete_files: bool = False) -> bool:
        """Cancel a download job and remove from qBittorrent"""
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return False
        
        if job.status in ['completed', 'failed', 'cancelled']:
            return True
        
        try:
            # If we have a torrent hash, delete from qBittorrent
            if job.torrent_hash:
                success = await qbittorrent_client.delete_torrent(
                    job.torrent_hash, 
                    delete_files=delete_files
                )
                if success:
                    job.status = "cancelled"
                    job.error_message = "Cancelled by user"
                    db.commit()
                    logger.info(f"Successfully cancelled download {job_id} and removed from qBittorrent")
                    return True
                else:
                    logger.error(f"Failed to delete torrent from qBittorrent for job {job_id}")
                    return False
            else:
                # No torrent hash yet, just mark as cancelled
                job.status = "cancelled"
                job.error_message = "Cancelled by user"
                db.commit()
                logger.info(f"Marked download {job_id} as cancelled (no torrent hash yet)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cancel download {job_id}: {e}")
            return False
    
    async def cleanup_completed_downloads(self, db: Session, older_than_days: int = 7):
        """Clean up old completed download records"""
        from sqlalchemy import and_
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        
        try:
            # Delete old completed downloads
            deleted_count = db.query(DownloadJob).filter(
                and_(
                    DownloadJob.status.in_(['completed', 'cancelled', 'failed']),
                    DownloadJob.created_at < cutoff_date
                )
            ).delete()
            
            db.commit()
            logger.info(f"Cleaned up {deleted_count} old download records")
            
        except Exception as e:
            logger.error(f"Failed to cleanup download records: {e}")
            db.rollback()

# Singleton instance
download_manager = DownloadManager()
