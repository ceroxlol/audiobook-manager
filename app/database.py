from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from .config import config

database_url = config.get('database.url')
engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Run migration to ensure all columns exist
    from .migrate import migrate_database
    migrate_database()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
