import asyncio
import time
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import logging
import os

from .qbittorrent import qbittorrent_client
from .prowlarr import prowlarr_client
from ..models import DownloadJob, SearchResult
from ..database import get_db

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self):
        self.active_downloads: Dict[str, asyncio.Task] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
    
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
            
            # Get the torrent hash (we'll need to monitor it)
            # Note: This is tricky with qBittorrent API. We'll monitor by checking all torrents.
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
        """Monitor download progress"""
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
            max_attempts = 120  # 10 minutes (5 second intervals)
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
                            download_job.status = "completed"
                            download_job.completed_at = time.time()
                            download_job.download_path = torrent.get('content_path', '')
                            db.commit()
                            logger.info(f"Download completed for job {job_id}")
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
                        if attempts > 20:  # After 100 seconds
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
        """Cancel a download job"""
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return False
        
        if job.status in ['completed', 'failed']:
            return True
        
        try:
            if job.torrent_hash:
                # Delete from qBittorrent
                success = await qbittorrent_client.delete_torrent(
                    job.torrent_hash, 
                    delete_files=delete_files
                )
                if success:
                    job.status = "cancelled"
                    db.commit()
                    return True
            else:
                # No torrent hash yet, just mark as cancelled
                job.status = "cancelled"
                db.commit()
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
