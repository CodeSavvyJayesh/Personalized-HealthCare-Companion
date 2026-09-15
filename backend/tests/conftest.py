import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("ENV", "test")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
