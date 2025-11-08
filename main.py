#!/usr/bin/env python3
"""
Audiobook Manager - Main Entry Point
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, '/opt/audiobook-manager')

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
