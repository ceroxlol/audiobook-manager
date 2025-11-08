#!/usr/bin/env python3
"""
Comprehensive test runner for Audiobook Manager
Run this after each phase to ensure everything works
"""
import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and print results"""
    print(f"\n{'='*60}")
    print(f"📋 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print(f"Command: {command}")
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print(f"Output:\n{result.stdout}")
        
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def main():
    """Run comprehensive test suite"""
    print("🎧 Audiobook Manager - Comprehensive Test Suite")
    print("Running tests for all phases...")
    
    # Phase 1: Foundation Tests
    phase1_success = run_command(
        "cd /opt/audiobook-manager && python -m pytest tests/unit/test_foundation.py -v",
        "Phase 1: Foundation Tests"
    )
    
    # Phase 2: Search Integration Tests
    phase2_success = run_command(
        "cd /opt/audiobook-manager && python -m pytest tests/integration/test_search.py -v",
        "Phase 2: Search Integration Tests"
    )
    
    # Phase 3: Download Integration Tests
    phase3_success = run_command(
        "cd /opt/audiobook-manager && python -m pytest tests/integration/test_download.py -v",
        "Phase 3: Download Integration Tests"
    )

    phase4_success = run_command(
    "cd /opt/audiobook-manager && python -m pytest tests/integration/test_audiobookshelf.py -v",
    "Phase 4: Audiobookshelf Integration Tests"
)
    
    # Functional Tests
    functional_success = run_command(
        "cd /opt/audiobook-manager && python -m pytest tests/functional/test_api.py -v",
        "Functional API Tests"
    )
    
    # Service Health Check
    health_success = run_command(
        "curl -f http://localhost:8000/health",
        "Service Health Check"
    )
    
    # API Endpoint Check
    api_success = run_command(
        "curl -f http://localhost:8000/api/v1/status",
        "API Status Endpoint Check"
    )
    
    # Print Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    tests = [
        ("Foundation", phase1_success),
        ("Search Integration", phase2_success),
        ("Download Integration", phase3_success),
        ("Audiobookshelf Integration", phase4_success),  # Add this line
        ("Functional API", functional_success),
        ("Service Health", health_success),
        ("API Status", api_success)
    ]
    
    all_passed = True
    for test_name, success in tests:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:25} {status}")
        if not success:
            all_passed = False
    
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())