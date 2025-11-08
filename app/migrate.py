#!/usr/bin/env python3
import sqlite3
import os
from .config import config

def migrate_database():
    """Migrate the database to the latest schema"""
    db_path = config.get('database.url').replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print("Database file doesn't exist yet. It will be created automatically.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if magnet_url column exists
        cursor.execute("PRAGMA table_info(search_results)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns
        if 'magnet_url' not in columns:
            print("Adding magnet_url column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN magnet_url TEXT")
        
        if 'quality' not in columns:
            print("Adding quality column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN quality TEXT")
        
        if 'format' not in columns:
            print("Adding format column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN format TEXT")
        
        if 'languages' not in columns:
            print("Adding languages column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN languages TEXT")
        
        if 'score' not in columns:
            print("Adding score column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN score REAL")
        
        if 'age_days' not in columns:
            print("Adding age_days column to search_results table...")
            cursor.execute("ALTER TABLE search_results ADD COLUMN age_days REAL")
        
        # Check download_jobs table
        cursor.execute("PRAGMA table_info(download_jobs)")
        download_job_columns = [column[1] for column in cursor.fetchall()]
        
        if 'error_message' not in download_job_columns:
            print("Adding error_message column to download_jobs table...")
            cursor.execute("ALTER TABLE download_jobs ADD COLUMN error_message TEXT")
        
        conn.commit()
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
