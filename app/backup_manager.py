import os
import shutil
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
import asyncio

from .config import config

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self):
        self.backup_dir = "/opt/audiobook-manager/backups"
        os.makedirs(self.backup_dir, exist_ok=True)
    
    async def create_backup(self) -> str:
        """Create a backup of database and configuration"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"backup_{timestamp}")
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            # Backup database
            db_path = config.get('database.url').replace('sqlite:///', '')
            if os.path.exists(db_path):
                backup_db_path = os.path.join(backup_path, "database.db")
                shutil.copy2(db_path, backup_db_path)
                logger.info(f"Database backed up to {backup_db_path}")
            
            # Backup configuration
            config_path = "/opt/audiobook-manager/config/settings.yaml"
            if os.path.exists(config_path):
                backup_config_path = os.path.join(backup_path, "settings.yaml")
                shutil.copy2(config_path, backup_config_path)
                logger.info(f"Configuration backed up to {backup_config_path}")
            
            # Backup logs (last 7 days)
            logs_dir = "/opt/audiobook-manager/logs"
            if os.path.exists(logs_dir):
                backup_logs_path = os.path.join(backup_path, "logs")
                shutil.copytree(logs_dir, backup_logs_path)
                logger.info(f"Logs backed up to {backup_logs_path}")
            
            logger.info(f"Backup completed: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise
    
    async def cleanup_old_backups(self, keep_count: int = 10):
        """Clean up old backups, keeping only the specified number"""
        try:
            backups = []
            for item in os.listdir(self.backup_dir):
                item_path = os.path.join(self.backup_dir, item)
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    backups.append((item_path, os.path.getctime(item_path)))
            
            # Sort by creation time (oldest first)
            backups.sort(key=lambda x: x[1])
            
            # Remove old backups
            for backup_path, _ in backups[:-keep_count]:
                shutil.rmtree(backup_path)
                logger.info(f"Removed old backup: {backup_path}")
                
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")