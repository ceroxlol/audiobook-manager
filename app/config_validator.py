import os
import logging
from typing import Dict, Any
from .config import config

logger = logging.getLogger(__name__)

class ConfigValidator:
    @staticmethod
    def validate() -> bool:
        """Validate configuration and return True if valid"""
        errors = []
        
        # Required configuration sections
        required_sections = ['app', 'server', 'integrations', 'storage', 'database']
        for section in required_sections:
            if config.get(section) is None:
                errors.append(f"Missing required configuration section: {section}")
        
        # Validate integrations
        integrations = ['qbittorrent', 'prowlarr', 'audiobookshelf']
        for integration in integrations:
            if not config.get(f'integrations.{integration}.host'):
                errors.append(f"Missing host for {integration}")
        
        # Validate storage paths
        storage_paths = ['download_path', 'library_path']
        for path_key in storage_paths:
            path = config.get(f'storage.{path_key}')
            if path:
                # Check if path is writable
                if not os.access(os.path.dirname(path) if os.path.dirname(path) else path, os.W_OK):
                    errors.append(f"Storage path not writable: {path}")
        
        # Log validation results
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return False
        else:
            logger.info("Configuration validation passed")
            return True
    
    @staticmethod
    def check_external_services() -> Dict[str, bool]:
        """Check connectivity to external services"""
        import asyncio
        from .services.prowlarr import prowlarr_client
        from .services.qbittorrent import qbittorrent_client
        from .services.audiobookshelf import audiobookshelf_client
        
        async def check_services():
            results = {}
            try:
                results['prowlarr'] = await prowlarr_client.test_connection()
            except Exception as e:
                logger.error(f"Prowlarr connection check failed: {e}")
                results['prowlarr'] = False
            
            try:
                results['qbittorrent'] = await qbittorrent_client.test_connection()
            except Exception as e:
                logger.error(f"qBittorrent connection check failed: {e}")
                results['qbittorrent'] = False
            
            try:
                results['audiobookshelf'] = await audiobookshelf_client.test_connection()
            except Exception as e:
                logger.error(f"Audiobookshelf connection check failed: {e}")
                results['audiobookshelf'] = False
            
            return results
        
        return asyncio.run(check_services())