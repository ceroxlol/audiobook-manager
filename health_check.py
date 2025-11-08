#!/usr/bin/env python3
"""
Quick health check for Audiobook Manager
Run this frequently to ensure basic functionality
"""
import requests
import sys

def check_endpoint(url, name):
    """Check if an endpoint is responding"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print(f"✅ {name}: UP (HTTP {response.status_code})")
            return True
        else:
            print(f"❌ {name}: DOWN (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"❌ {name}: ERROR ({e})")
        return False

def main():
    base_url = "http://localhost:8000"
    
    print("🔍 Audiobook Manager - Quick Health Check")
    print("=" * 50)
    
    endpoints = [
        ("/health", "Health Check"),
        ("/api/v1/status", "API Status"),
        ("/api/v1/queue", "Download Queue"),
        ("/", "Web Interface")
    ]
    
    all_healthy = True
    for endpoint, name in endpoints:
        if not check_endpoint(f"{base_url}{endpoint}", name):
            all_healthy = False
    
    print("=" * 50)
    if all_healthy:
        print("🎉 All systems operational!")
        return 0
    else:
        print("💥 Some systems are down!")
        return 1

if __name__ == "__main__":
    sys.exit(main())