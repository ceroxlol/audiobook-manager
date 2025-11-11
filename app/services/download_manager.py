import asyncio
import time
import os
import shutil
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import logging

from .qbittorrent import qbittorrent_client
from .prowlarr import prowlarr_client
from .audiobookshelf import audiobookshelf_client
from .file_manager import FileManager
from ..models import DownloadJob, SearchResult
from ..database import get_db, SessionLocal
from ..config import config

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
        Start downloading a search result with better tagging
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
            
            # Create unique tag for this download
            unique_tag = f"audiobook-manager-{download_job.id}"
            
            # Add to qBittorrent with better tagging
            success = await qbittorrent_client.add_torrent(
                torrent_url=download_url,
                category="audiobooks",
                tags=[unique_tag, "audiobook-manager"]  # Multiple tags for better tracking
            )
            
            if not success:
                download_job.status = "failed"
                download_job.error_message = "Failed to add torrent to qBittorrent"
                db.commit()
                return download_job
            
            download_job.status = "downloading"
            db.commit()
            
            logger.info(f"Started download for: {result.title} (Job: {download_job.id}, Tag: {unique_tag})")
            
            # Start monitoring this download (don't pass db session)
            await self._start_monitoring(download_job.id)
            
            return download_job
            
        except Exception as e:
            logger.error(f"Failed to start download {search_result_id}: {e}")
            download_job.status = "failed"
            download_job.error_message = str(e)
            db.commit()
            return download_job
    
    async def _start_monitoring(self, job_id: int):
        """Start monitoring a download job"""
        if job_id in self.monitoring_tasks:
            return
        
        task = asyncio.create_task(self._monitor_download(job_id))
        self.monitoring_tasks[job_id] = task
    
    async def _monitor_download(self, job_id: int):
        """Monitor download progress with improved torrent matching"""
        logger.info(f"Started monitoring download job {job_id}")
        
        try:
            # Create a new database session for this monitoring task
            db = SessionLocal()
            
            try:
                download_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                if not download_job:
                    logger.error(f"Download job {job_id} not found for monitoring")
                    return
                
                search_result = db.query(SearchResult).filter(SearchResult.id == download_job.search_result_id).first()
                if not search_result:
                    logger.error(f"Search result for job {job_id} not found")
                    return
            finally:
                db.close()
            
            # We'll check for the torrent by looking for our tag AND by matching the title
            target_tag = f"audiobook-manager-{job_id}"
            max_attempts = 1200  # 100 minutes (5 second intervals) - longer timeout for large files
            attempts = 0
            torrent_hash = None
            
            while attempts < max_attempts:
                attempts += 1
                
                # Create a fresh database session for each update
                db = SessionLocal()
                
                try:
                    # Refresh the download_job from database
                    download_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                    if not download_job:
                        logger.error(f"Download job {job_id} disappeared during monitoring")
                        break
                    
                    # Check if job was cancelled
                    if download_job.status in ['cancelled', 'completed', 'failed']:
                        logger.info(f"Download job {job_id} is {download_job.status}, stopping monitoring")
                        break
                    
                    # Get all torrents in audiobooks category
                    torrents = await qbittorrent_client.get_torrents(category="audiobooks")
                    
                    # Find our torrent - try multiple strategies
                    matching_torrent = None
                    
                    # Strategy 1: Look for our specific tag
                    for torrent in torrents:
                        if target_tag in torrent.get('tags', ''):
                            matching_torrent = torrent
                            break
                    
                    # Strategy 2: Look for torrents with similar names (fallback)
                    if not matching_torrent:
                        search_title_lower = search_result.title.lower()
                        for torrent in torrents:
                            torrent_name = torrent.get('name', '').lower()
                            # Check if the search result title is in the torrent name
                            if search_title_lower in torrent_name:
                                # Additional check: make sure this isn't someone else's torrent
                                # by checking if it was added around the same time as our job
                                torrent_added = torrent.get('added_on', 0)
                                job_created = download_job.created_at.timestamp() if download_job.created_at else 0
                                time_diff = abs(torrent_added - job_created)
                                
                                if time_diff < 300:  # Within 5 minutes
                                    matching_torrent = torrent
                                    logger.info(f"Found torrent by name match: {torrent_name}")
                                    break
                    
                    if matching_torrent:
                        torrent_hash = matching_torrent.get('hash')
                        torrent_name = matching_torrent.get('name', 'Unknown')
                        
                        # Update job with torrent hash if not set
                        if not download_job.torrent_hash:
                            download_job.torrent_hash = torrent_hash
                            logger.info(f"Associated torrent {torrent_hash} with job {job_id}")
                            # Log torrent details for debugging
                            logger.debug(f"Torrent details: save_path={matching_torrent.get('save_path')}, "
                                       f"content_path={matching_torrent.get('content_path')}, "
                                       f"name={torrent_name}, state={matching_torrent.get('state')}")
                        
                        # Update progress
                        progress = matching_torrent.get('progress', 0) * 100
                        previous_progress = download_job.progress
                        download_job.progress = progress
                        
                        # Log progress changes
                        if progress != previous_progress:
                            logger.debug(f"Download progress for job {job_id}: {progress:.1f}%")
                        
                        # Check status
                        state = matching_torrent.get('state', '')
                        
                        if progress >= 99.9:  # Use 99.9% to account for rounding
                            # Download completed - process the audiobook
                            # Get torrent name to find it in download_path
                            torrent_name = matching_torrent.get('name', '')
                            
                            # The file should be in our download_path (mapped from qBittorrent)
                            download_path_base = config.get('storage.download_path')
                            download_path = os.path.join(download_path_base, torrent_name)
                            
                            download_job.download_path = download_path
                            download_job.status = "processing"
                            db.commit()
                            
                            logger.info(f"Download completed for job {job_id}: {torrent_name}")
                            logger.info(f"Looking for files in: {download_path}")
                            
                            # Wait a moment for filesystem to sync
                            await asyncio.sleep(2)
                            
                            # Process the completed download (pass a fresh db session)
                            process_db = SessionLocal()
                            try:
                                # Refresh objects in new session
                                download_job = process_db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                                search_result = process_db.query(SearchResult).filter(SearchResult.id == download_job.search_result_id).first()
                                await self._process_completed_download(download_job, search_result, process_db)
                            finally:
                                process_db.close()
                            break
                            
                        elif state in ['error', 'missingFiles', 'pausedUP', 'unknown']:
                            download_job.status = "failed"
                            download_job.error_message = f"Torrent state: {state}"
                            db.commit()
                            logger.error(f"Download failed for job {job_id}: {state}")
                            break
                        else:
                            download_job.status = "downloading"
                            db.commit()
                    
                    else:
                        # Torrent not found yet
                        if attempts == 1:
                            logger.info(f"Waiting for torrent to appear in qBittorrent for job {job_id}")
                        elif attempts % 12 == 0:  # Log every minute
                            logger.info(f"Still waiting for torrent for job {job_id} (attempt {attempts})")
                        
                        if attempts > 120:  # After 10 minutes without finding torrent
                            download_job.status = "failed"
                            download_job.error_message = "Torrent not found in qBittorrent after timeout"
                            db.commit()
                            logger.error(f"Torrent not found for job {job_id} after {attempts} attempts")
                            break
                
                except Exception as e:
                    logger.error(f"Error monitoring download job {job_id}: {e}")
                    # Don't break on temporary errors, just continue monitoring
                finally:
                    # Always close the database session
                    db.close()
                
                # Wait before next check
                await asyncio.sleep(5)
            
            # Cleanup monitoring task
            if job_id in self.monitoring_tasks:
                del self.monitoring_tasks[job_id]
            logger.info(f"Stopped monitoring download job {job_id}")
                
        except Exception as e:
            logger.error(f"Monitoring task failed for job {job_id}: {e}")
            if job_id in self.monitoring_tasks:
                del self.monitoring_tasks[job_id]

    async def _process_completed_download(self, 
                                    download_job: DownloadJob, 
                                    search_result: SearchResult, 
                                    db: Session):
        """Process a completed download - move to library and notify Audiobookshelf"""
        try:
            download_job.status = "processing"
            db.commit()
            
            logger.info(f"Processing completed download: {search_result.title}")
            
            # Move the downloaded files from download_path to library_path
            organization_result = await self.file_manager.organize_downloaded_audiobook(
                download_job.download_path
            )
            
            if not organization_result:
                download_job.status = "failed"
                download_job.error_message = "Failed to organize downloaded files"
                db.commit()
                return
            
            # Trigger Audiobookshelf library scan so it picks up the new audiobook
            libraries = await audiobookshelf_client.get_libraries()
            if libraries:
                for library in libraries:
                    scan_success = await audiobookshelf_client.scan_library(library['id'])
                    if scan_success:
                        logger.info(f"Triggered library scan for {library.get('name', library['id'])}")
                
                from datetime import datetime
                download_job.status = "completed"
                download_job.completed_at = datetime.now()
                logger.info(f"Successfully processed download: {search_result.title}")
            else:
                download_job.status = "completed_with_warning"
                download_job.error_message = "Download completed but could not trigger Audiobookshelf scan"
                logger.warning(f"Download completed but Audiobookshelf scan failed: {search_result.title}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Failed to process completed download {download_job.id}: {e}")
            download_job.status = "failed"
            download_job.error_message = f"Processing failed: {str(e)}"
            db.commit()
    
    async def delete_download_job(self, job_id: int, db: Session, delete_files: bool = True) -> bool:
        """Delete a download job from database and optionally delete downloaded files"""
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            logger.warning(f"Download job {job_id} not found")
            return False
        
        try:
            # If the job has files and we want to delete them
            if delete_files and job.download_path and os.path.exists(job.download_path):
                try:
                    if os.path.isfile(job.download_path):
                        os.remove(job.download_path)
                        logger.info(f"Deleted file: {job.download_path}")
                    else:
                        shutil.rmtree(job.download_path)
                        logger.info(f"Deleted directory: {job.download_path}")
                except Exception as e:
                    logger.error(f"Failed to delete files for job {job_id}: {e}")
            
            # If the job has a torrent in qBittorrent, remove it
            if job.torrent_hash:
                try:
                    await qbittorrent_client.delete_torrent(job.torrent_hash, delete_files=delete_files)
                    logger.info(f"Deleted torrent {job.torrent_hash} from qBittorrent")
                except Exception as e:
                    logger.error(f"Failed to delete torrent for job {job_id}: {e}")
            
            # Delete the job from database
            db.delete(job)
            db.commit()
            logger.info(f"Deleted download job {job_id} from database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete download job {job_id}: {e}")
            db.rollback()
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
        """Clean up old completed, failed, and cancelled download records"""
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=older_than_days)

        try:
            # Find all jobs that are completed, failed, or cancelled and old enough
            jobs_to_delete = db.query(DownloadJob).filter(
                DownloadJob.status.in_(['completed', 'cancelled', 'failed']),
                DownloadJob.created_at < cutoff_date
            ).all()

            deleted_count = 0
            for job in jobs_to_delete:
                logger.info(f"Cleaning up old job {job.id} ({job.status}) created at {job.created_at}")
                
                # Delete any remaining files in download_path
                if job.download_path and os.path.exists(job.download_path):
                    try:
                        if os.path.isfile(job.download_path):
                            os.remove(job.download_path)
                        else:
                            shutil.rmtree(job.download_path)
                        logger.info(f"Deleted files for job {job.id}: {job.download_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete files for job {job.id}: {e}")
                
                # Delete from database
                db.delete(job)
                deleted_count += 1

            db.commit()
            logger.info(f"Cleaned up {deleted_count} old download records (failed, cancelled, completed)")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup download records: {e}")
            db.rollback()
            return 0

# Singleton instance
download_manager = DownloadManager()
