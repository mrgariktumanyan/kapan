import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="kapan_test_")
os.environ.setdefault("KAPAN_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("KAPAN_STORAGE_DIR", f"{_tmp}/storage")
os.environ.setdefault("KAPAN_ADMIN_PASSWORD", "admin-password")
os.environ.setdefault("KAPAN_RUN_JOBS_INLINE", "1")
os.environ.setdefault("KAPAN_SECRET_KEY", "test-secret-key-0123456789abcdef0123456789")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
