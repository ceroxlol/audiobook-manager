#!/usr/bin/env python3
"""
Migration script to add 'source' column to search_results table
Run this once to update existing database records
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, '/opt/audiobook-manager')

from app.database import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Add source column to search_results table if it doesn't exist"""
    db = SessionLocal()
    
    try:
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(search_results)"))
        columns = [row[1] for row in result]
        
        if 'source' not in columns:
            logger.info("Adding 'source' column to search_results table...")
            
            # Add the column with default value 'prowlarr'
            db.execute(text("ALTER TABLE search_results ADD COLUMN source VARCHAR DEFAULT 'prowlarr'"))
            
            # Update all existing records to have source='prowlarr'
            db.execute(text("UPDATE search_results SET source = 'prowlarr' WHERE source IS NULL"))
            
            db.commit()
            logger.info("✓ Successfully added 'source' column to search_results table")
            logger.info("✓ All existing records set to source='prowlarr'")
        else:
            logger.info("'source' column already exists in search_results table")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Starting database migration...")
    migrate_database()
    logger.info("Migration completed successfully!")
