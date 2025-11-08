import psutil
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SystemMonitor:
    @staticmethod
    async def get_system_stats() -> Dict[str, Any]:
        """Get system statistics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Process info
            process = psutil.Process()
            process_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / 1024 / 1024 / 1024,
                'memory_total_gb': memory.total / 1024 / 1024 / 1024,
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / 1024 / 1024 / 1024,
                'disk_total_gb': disk.total / 1024 / 1024 / 1024,
                'process_memory_mb': process_memory,
                'active_downloads': 0,  # Would need to track this
            }
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {}
    
    @staticmethod
    async def check_disk_space() -> bool:
        """Check if there's sufficient disk space"""
        try:
            disk = psutil.disk_usage('/')
            return disk.percent < 90  # Alert if usage > 90%
        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return False