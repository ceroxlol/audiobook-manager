#!/usr/bin/env python3
import asyncio
import aiohttp
import sys
import os

# Add the app directory to Python path
sys.path.append('/opt/audiobook-manager')

from app.services.qbittorrent import QBittorrentClient
from app.services.prowlarr import ProwlarrClient
from app.config import config

async def test_qbittorrent():
    print("Testing qBittorrent connection...")
    
    # Print connection details (mask password)
    qbt_host = config.get('integrations.qbittorrent.host')
    qbt_port = config.get('integrations.qbittorrent.port')
    qbt_user = config.get('integrations.qbittorrent.username')
    
    print(f"Connecting to: http://{qbt_host}:{qbt_port}")
    print(f"Username: {qbt_user}")
    
    client = QBittorrentClient()
    try:
        # Test basic connection first
        async with aiohttp.ClientSession() as session:
            test_url = f"http://{qbt_host}:{qbt_port}/api/v2/app/version"
            print(f"Testing URL: {test_url}")
            
            try:
                async with session.get(test_url, timeout=10) as response:
                    print(f"HTTP Status: {response.status}")
                    if response.status == 200:
                        version = await response.text()
                        print(f"qBittorrent version: {version}")
                    else:
                        print(f"Error: {await response.text()}")
            except Exception as e:
                print(f"HTTP test failed: {e}")
        
        # Test login
        print("\nTesting login...")
        success = await client.login()
        if success:
            print("✅ Login successful!")
            
            # Test API call
            print("Testing API call...")
            version = await client._make_request('get', 'app/version')
            print(f"API Version: {version}")
            
        else:
            print("❌ Login failed!")
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
    
    finally:
        if client.session:
            await client.session.close()

async def test_prowlarr():
    print("\nTesting Prowlarr connection...")
    
    prowlarr_host = config.get('integrations.prowlarr.host')
    prowlarr_port = config.get('integrations.prowlarr.port')
    
    print(f"Connecting to: http://{prowlarr_host}:{prowlarr_port}")
    
    client = ProwlarrClient()
    try:
        success = await client.test_connection()
        if success:
            print("✅ Prowlarr connection successful!")
        else:
            print("❌ Prowlarr connection failed!")
    except Exception as e:
        print(f"❌ Prowlarr test failed: {e}")

async def main():
    print("=== Connection Debug Tool ===")
    await test_qbittorrent()
    await test_prowlarr()

if __name__ == "__main__":
    asyncio.run(main())
