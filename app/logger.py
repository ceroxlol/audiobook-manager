import logging
import os
from .config import config

def setup_logging():
    """Setup application logging"""
    log_level = config.get('logging.level', 'INFO')
    log_file = config.get('logging.file', '/opt/audiobook-manager/logs/app.log')
    
    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging setup completed")
