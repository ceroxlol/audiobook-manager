#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/audiobook-manager')

print("Python path:")
for path in sys.path:
    print(f"  {path}")

print("\nTesting imports...")

try:
    from app.config import config
    print("✅ app.config import successful")
except Exception as e:
    print(f"❌ app.config failed: {e}")

try:
    from app.database import init_db
    print("✅ app.database import successful")
except Exception as e:
    print(f"❌ app.database failed: {e}")

try:
    from app.api.endpoints import router
    print("✅ app.api.endpoints import successful")
except Exception as e:
    print(f"❌ app.api.endpoints failed: {e}")

try:
    from app.main import app
    print("✅ app.main import successful")
except Exception as e:
    print(f"❌ app.main failed: {e}")
