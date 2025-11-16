from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import asyncio

from ..database import get_db
from ..models import SearchResult, DownloadJob
from ..services.search import search_service
from ..services.prowlarr import prowlarr_client
from ..services.qbittorrent import qbittorrent_client
from ..services.audiobookshelf import audiobookshelf_client
from ..services.audiobookbay import audiobookbay_client
from ..services.download_manager import download_manager
from ..system_monitor import SystemMonitor
from ..backup_manager import BackupManager
from ..config_validator import ConfigValidator

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/search")
async def search_audiobooks(
    query: str = Query(..., description="Search query for audiobooks"),
    sources: Optional[str] = Query(None, description="Comma-separated list of sources: prowlarr,audiobookbay"),
    db: Session = Depends(get_db)
):
    """Search for audiobooks from multiple sources"""
    try:
        # Parse sources parameter
        source_list = None
        if sources:
            source_list = [s.strip() for s in sources.split(',') if s.strip()]
        
        results = await search_service.search_audiobooks(query, db, sources=source_list)
        return {
            "query": query,
            "sources": source_list or ["prowlarr", "audiobookbay"],
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/search/recent")
async def get_recent_searches(
    limit: int = Query(10, description="Number of recent searches to return"),
    db: Session = Depends(get_db)
):
    """Get recent search queries"""
    try:
        recent = await search_service.get_recent_searches(db, limit)
        return {"recent_searches": recent}
    except Exception as e:
        logger.error(f"Failed to get recent searches: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent searches")

@router.post("/download/{result_id}")
async def download_audiobook(
    result_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger download for a search result"""
    try:
        # Get the search result
        result = db.query(SearchResult).filter(SearchResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Search result not found")
        
        # Start download
        download_job = await download_manager.start_download(result_id, db)
        
        if not download_job:
            raise HTTPException(status_code=500, detail="Failed to start download")
        
        return {
            "message": "Download started",
            "job_id": download_job.id,
            "title": result.title,
            "status": download_job.status
        }
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@router.get("/download/status/{job_id}")
async def get_download_status(
    job_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed download status"""
    try:
        status = await download_manager.get_download_status(job_id, db)
        if not status:
            raise HTTPException(status_code=404, detail="Download job not found")
        
        return status
    except Exception as e:
        logger.error(f"Failed to get download status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get download status: {str(e)}")

@router.delete("/download/{job_id}")
async def cancel_download(
    job_id: int,
    delete_files: bool = Query(False, description="Delete downloaded files"),
    db: Session = Depends(get_db)
):
    """Cancel a download job and remove from qBittorrent"""
    try:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Download job not found")
        
        success = await download_manager.cancel_download(job_id, db, delete_files)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to cancel download")
        
        return {"message": "Download cancelled successfully"}
    except Exception as e:
        logger.error(f"Failed to cancel download: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel download: {str(e)}")

@router.delete("/queue/job/{job_id}")
async def delete_download_job(
    job_id: int,
    delete_files: bool = Query(True, description="Delete downloaded files"),
    db: Session = Depends(get_db)
):
    """Delete a download job from queue and optionally delete its files"""
    try:
        success = await download_manager.delete_download_job(job_id, db, delete_files)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete download job")
        
        return {"message": "Download job deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete download job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete download job: {str(e)}")

@router.get("/queue")
async def get_download_queue(db: Session = Depends(get_db)):
    """Get current download queue with detailed status"""
    try:
        downloads = db.query(DownloadJob).order_by(DownloadJob.created_at.desc()).limit(50).all()
        
        # Get detailed status for each download
        detailed_downloads = []
        for job in downloads:
            result = db.query(SearchResult).filter(SearchResult.id == job.search_result_id).first()
            
            download_info = {
                "id": job.id,
                "search_result_id": job.search_result_id,
                "title": result.title if result else "Unknown",
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error_message": job.error_message,
                "torrent_hash": job.torrent_hash
            }
            
            # Add torrent details if available and downloading
            if job.status == "downloading" and job.torrent_hash:
                try:
                    torrent = await qbittorrent_client.get_torrent(job.torrent_hash)
                    if torrent:
                        download_info.update({
                            "download_speed": torrent.get('dlspeed', 0),
                            "upload_speed": torrent.get('upspeed', 0),
                            "size": torrent.get('size', 0),
                            "downloaded": torrent.get('downloaded', 0),
                            "eta": torrent.get('eta', 0),
                            "seeds": torrent.get('num_seeds', 0),
                            "peers": torrent.get('num_leechs', 0),
                            "state": torrent.get('state', 'unknown'),
                            "torrent_name": torrent.get('name', 'Unknown')
                        })
                except Exception as e:
                    logger.debug(f"Could not get torrent details for {job.torrent_hash}: {e}")
                    download_info['torrent_error'] = str(e)
            
            detailed_downloads.append(download_info)
        
        return {
            "downloads": detailed_downloads,
            "total": len(detailed_downloads),
            "active": len([d for d in detailed_downloads if d['status'] in ['starting', 'downloading', 'processing']])
        }
    except Exception as e:
        logger.error(f"Failed to get download queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get download queue: {str(e)}")

@router.post("/queue/cleanup")
async def cleanup_queue(
    older_than_days: int = Query(7, description="Clean up records older than X days"),
    db: Session = Depends(get_db)
):
    """Clean up old download records"""
    try:
        deleted_count = await download_manager.cleanup_completed_downloads(db, older_than_days)
        return {
            "message": f"Cleaned up {deleted_count} records older than {older_than_days} days",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

@router.get("/status")
async def get_system_status():
    """Get system status and integration health"""
    try:
        # Test connections
        prowlarr_connected = await prowlarr_client.test_connection()
        qbittorrent_connected = await qbittorrent_client.test_connection()
        audiobookshelf_connected = await audiobookshelf_client.test_connection()
        audiobookbay_connected = await audiobookbay_client.test_connection()
        
        # Get additional info
        download_speed = 0
        if qbittorrent_connected:
            download_speed = await qbittorrent_client.get_download_speed()
        
        libraries = []
        if audiobookshelf_connected:
            libraries = await audiobookshelf_client.get_libraries()
        
        # Get AudiobookBay active domain
        audiobookbay_domain = audiobookbay_client.get_active_domain()
        
        status = "operational"
        if not all([prowlarr_connected, qbittorrent_connected, audiobookshelf_connected]):
            status = "degraded"
        
        return {
            "status": status,
            "integrations": {
                "prowlarr": {
                    "connected": prowlarr_connected,
                    "status": "connected" if prowlarr_connected else "disconnected"
                },
                "qbittorrent": {
                    "connected": qbittorrent_connected,
                    "status": "connected" if qbittorrent_connected else "disconnected",
                    "download_speed": download_speed
                },
                "audiobookshelf": {
                    "connected": audiobookshelf_connected,
                    "status": "connected" if audiobookshelf_connected else "disconnected",
                    "libraries": len(libraries),
                    "library_names": [lib.get('name', 'Unknown') for lib in libraries]
                },
                "audiobookbay": {
                    "connected": audiobookbay_connected,
                    "status": "connected" if audiobookbay_connected else "disconnected",
                    "active_domain": audiobookbay_domain if audiobookbay_connected else None,
                    "available_domains": audiobookbay_client.domains if audiobookbay_client.enabled else []
                }
            }
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "integrations": {
                "prowlarr": {"connected": False, "status": "error"},
                "qbittorrent": {"connected": False, "status": "error"},
                "audiobookshelf": {"connected": False, "status": "error"},
                "audiobookbay": {"connected": False, "status": "error"}
            }
        }

@router.get("/audiobookshelf/libraries")
async def get_audiobookshelf_libraries():
    """Get Audiobookshelf libraries"""
    try:
        libraries = await audiobookshelf_client.get_libraries()
        return {"libraries": libraries}
    except Exception as e:
        logger.error(f"Failed to get Audiobookshelf libraries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get libraries: {str(e)}")

@router.post("/audiobookshelf/scan/{library_id}")
async def scan_audiobookshelf_library(library_id: str):
    """Trigger Audiobookshelf library scan"""
    try:
        success = await audiobookshelf_client.scan_library(library_id)
        if success:
            return {"message": f"Library {library_id} scan triggered"}
        else:
            raise HTTPException(status_code=500, detail="Failed to trigger library scan")
    except Exception as e:
        logger.error(f"Failed to scan library {library_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan library: {str(e)}")
    
@router.get("/system/stats")
async def get_system_stats():
    """Get system statistics"""
    try:
        stats = await SystemMonitor.get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system statistics")

@router.post("/system/backup")
async def create_backup(background_tasks: BackgroundTasks):
    """Create a system backup"""
    try:
        backup_manager = BackupManager()
        background_tasks.add_task(backup_manager.create_backup)
        return {"message": "Backup started in background"}
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail="Backup failed")

@router.get("/system/health")
async def get_system_health():
    """Comprehensive system health check"""
    try:
        # Validate configuration
        config_valid = ConfigValidator.validate()
        
        # Check external services
        service_status = await ConfigValidator.check_external_services()
        
        # Check disk space
        disk_ok = await SystemMonitor.check_disk_space()
        
        # Get system stats
        system_stats = await SystemMonitor.get_system_stats()
        
        overall_health = (
            config_valid and 
            all(service_status.values()) and 
            disk_ok and
            system_stats.get('disk_percent', 100) < 90
        )
        
        return {
            "healthy": overall_health,
            "config_valid": config_valid,
            "services": service_status,
            "disk_ok": disk_ok,
            "system_stats": system_stats
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "healthy": False,
            "error": str(e)
        }
    
@router.get("/debug/qbittorrent")
async def debug_qbittorrent():
    """Debug endpoint to check qBittorrent status"""
    try:
        # Get all torrents
        torrents = await qbittorrent_client.get_torrents()
        audiobooks_torrents = await qbittorrent_client.get_torrents(category="audiobooks")
        
        return {
            "total_torrents": len(torrents),
            "audiobooks_torrents": len(audiobooks_torrents),
            "audiobooks_torrents_list": [
                {
                    "name": t.get('name'),
                    "hash": t.get('hash'),
                    "progress": t.get('progress', 0) * 100,
                    "state": t.get('state'),
                    "tags": t.get('tags', ''),
                    "size": t.get('size', 0),
                    "downloaded": t.get('downloaded', 0)
                }
                for t in audiobooks_torrents
            ]
        }
    except Exception as e:
        logger.error(f"Debug endpoint failed: {e}")
        return {"error": str(e)}