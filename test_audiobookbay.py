#!/usr/bin/env python3
"""
Test script for AudiobookBay client
"""
import sys
import os
import asyncio
import logging

# Add the current directory to Python path
sys.path.insert(0, '/opt/audiobook-manager')

from app.services.audiobookbay import audiobookbay_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_connection():
    """Test connection to AudiobookBay"""
    logger.info("Testing connection to AudiobookBay...")
    connected = await audiobookbay_client.test_connection()
    
    if connected:
        logger.info("✓ Successfully connected to AudiobookBay")
        return True
    else:
        logger.error("✗ Failed to connect to AudiobookBay")
        logger.error("This might be due to:")
        logger.error("  - Domain has changed (update config/settings.yaml)")
        logger.error("  - Site is down")
        logger.error("  - Network/firewall issues")
        return False

async def test_search():
    """Test searching for audiobooks"""
    test_queries = ["Harry Potter", "Stephen King", "Tolkien"]
    
    for query in test_queries:
        logger.info(f"\n{'='*60}")
        logger.info(f"Searching for: {query}")
        logger.info(f"{'='*60}")
        
        results = await audiobookbay_client.search(query)
        
        if results:
            logger.info(f"✓ Found {len(results)} results")
            
            # Show first 3 results
            for i, result in enumerate(results[:3], 1):
                logger.info(f"\n  Result #{i}:")
                logger.info(f"    Title: {result['title']}")
                logger.info(f"    Author: {result['author']}")
                logger.info(f"    Narrator: {result['narrator']}")
                logger.info(f"    Format: {result['format']}")
                logger.info(f"    Quality: {result['quality']}")
                logger.info(f"    Size: {result['size']} bytes")
                logger.info(f"    Score: {result['score']:.1f}")
                logger.info(f"    Has Magnet: {'Yes' if result['magnet_url'] else 'No'}")
        else:
            logger.warning(f"✗ No results found for: {query}")

async def main():
    """Main test function"""
    logger.info("Starting AudiobookBay Client Test")
    logger.info("="*60)
    
    # Test 1: Connection
    if not await test_connection():
        logger.error("\nConnection test failed. Aborting further tests.")
        return
    
    # Test 2: Search
    logger.info("\n")
    await test_search()
    
    logger.info("\n" + "="*60)
    logger.info("AudiobookBay Client Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
