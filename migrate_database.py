#!/usr/bin/env python3
import sqlite3
import os
import sys

# Add the app directory to Python path
sys.path.append('/opt/audiobook-manager')

from app.database import engine, SessionLocal
from app.models import Base

def migrate_database():
    """Migrate the database to the new schema"""
    db_path = '/opt/audiobook-manager/data/database.db'
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet, creating new one...")
        Base.metadata.create_all(bind=engine)
        return
    
    # Backup the existing database
    backup_path = f"{db_path}.backup"
    if os.path.exists(backup_path):
        os.remove(backup_path)
    os.rename(db_path, backup_path)
    print(f"Backed up existing database to {backup_path}")
    
    # Create new database with updated schema
    Base.metadata.create_all(bind=engine)
    print("Created new database schema")
    
    # If you need to migrate data, you would do it here
    # For now, we'll start with a fresh database since we're in development
    print("Migration completed. Starting with fresh database.")

if __name__ == "__main__":
    migrate_database()
