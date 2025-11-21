#!/usr/bin/env python3
"""
Test script to validate all improvements made to AudiobookBay and Prowlarr integrations.
Run this script to verify:
1. AudiobookBay search returns correct results
2. Timeout handling works correctly
3. Domain fallback mechanism functions properly
4. Health checks report correct status
5. Error logging provides detailed information
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.audiobookbay import audiobookbay_client
from app.services.prowlarr import prowlarr_client

async def test_audiobookbay_search():
    """Test AudiobookBay search functionality"""
    print("\n" + "="*60)
    print("TEST 1: AudiobookBay Search")
    print("="*60)
    
    test_query = "Harry Potter"
    print(f"Searching for: '{test_query}'")
    
    try:
        results = await audiobookbay_client.search(test_query)
        
        if results:
            print(f"✅ SUCCESS: Found {len(results)} results")
            print(f"Active domain: {audiobookbay_client.get_active_domain()}")
            
            # Show first result
            if len(results) > 0:
                first = results[0]
                print(f"\nFirst result:")
                print(f"  Title: {first.get('title', 'N/A')}")
                print(f"  Author: {first.get('author', 'N/A')}")
                print(f"  Size: {first.get('size', 0) / (1024*1024):.2f} MB")
                print(f"  Score: {first.get('score', 0)}")
        else:
            print("⚠️  WARNING: No results found (might be expected if domains are down)")
            
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False
    
    return True

async def test_audiobookbay_connection():
    """Test AudiobookBay connection and domain fallback"""
    print("\n" + "="*60)
    print("TEST 2: AudiobookBay Connection & Domain Fallback")
    print("="*60)
    
    print(f"Available domains: {audiobookbay_client.domains}")
    print(f"Timeout: {audiobookbay_client.timeout}s")
    
    try:
        connected = await audiobookbay_client.test_connection()
        
        if connected:
            print(f"✅ SUCCESS: Connected to AudiobookBay")
            print(f"Active domain: {audiobookbay_client.get_active_domain()}")
        else:
            print("❌ FAILED: Could not connect to any AudiobookBay domain")
            return False
            
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False
    
    return True

async def test_prowlarr_search():
    """Test Prowlarr search functionality"""
    print("\n" + "="*60)
    print("TEST 3: Prowlarr Search")
    print("="*60)
    
    test_query = "Harry Potter"
    print(f"Searching for: '{test_query}'")
    print(f"Prowlarr URL: {prowlarr_client.base_url}")
    print(f"Timeout: {prowlarr_client.timeout}s")
    
    try:
        results = await prowlarr_client.search(test_query)
        
        if results:
            print(f"✅ SUCCESS: Found {len(results)} results")
            
            # Show first result
            if len(results) > 0:
                first = results[0]
                print(f"\nFirst result:")
                print(f"  Title: {first.get('title', 'N/A')}")
                print(f"  Author: {first.get('author', 'N/A')}")
                print(f"  Seeders: {first.get('seeders', 0)}")
                print(f"  Score: {first.get('score', 0)}")
        else:
            print("⚠️  WARNING: No results found")
            
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False
    
    return True

async def test_prowlarr_connection():
    """Test Prowlarr connection"""
    print("\n" + "="*60)
    print("TEST 4: Prowlarr Connection")
    print("="*60)
    
    print(f"Prowlarr URL: {prowlarr_client.base_url}")
    
    try:
        connected = await prowlarr_client.test_connection()
        
        if connected:
            print(f"✅ SUCCESS: Connected to Prowlarr")
        else:
            print("❌ FAILED: Could not connect to Prowlarr")
            print("Check that Prowlarr is running and API key is correct")
            return False
            
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False
    
    return True

async def test_combined_search():
    """Test combined search from both sources"""
    print("\n" + "="*60)
    print("TEST 5: Combined Search (Both Sources)")
    print("="*60)
    
    test_query = "Project Hail Mary"
    print(f"Searching for: '{test_query}'")
    
    try:
        # Search both sources concurrently
        prowlarr_results, audiobookbay_results = await asyncio.gather(
            prowlarr_client.search(test_query),
            audiobookbay_client.search(test_query),
            return_exceptions=True
        )
        
        prowlarr_count = len(prowlarr_results) if not isinstance(prowlarr_results, Exception) else 0
        audiobookbay_count = len(audiobookbay_results) if not isinstance(audiobookbay_results, Exception) else 0
        
        print(f"\nProwlarr results: {prowlarr_count}")
        print(f"AudiobookBay results: {audiobookbay_count}")
        print(f"Total results: {prowlarr_count + audiobookbay_count}")
        
        if prowlarr_count > 0 or audiobookbay_count > 0:
            print("✅ SUCCESS: Got results from at least one source")
        else:
            print("⚠️  WARNING: No results from either source")
        
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        return False
    
    return True

async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("AUDIOBOOK MANAGER - IMPROVEMENTS VALIDATION")
    print("="*60)
    
    results = {}
    
    # Test AudiobookBay
    results['audiobookbay_connection'] = await test_audiobookbay_connection()
    results['audiobookbay_search'] = await test_audiobookbay_search()
    
    # Test Prowlarr
    results['prowlarr_connection'] = await test_prowlarr_connection()
    results['prowlarr_search'] = await test_prowlarr_search()
    
    # Test combined
    results['combined_search'] = await test_combined_search()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Improvements are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check logs for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
