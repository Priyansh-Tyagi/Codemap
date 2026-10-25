"""Container health probe: exit 0 if /api/health answers 200, else 1.

Stdlib only (python:slim has no curl). If CODEMAP_ALLOWED_HOSTS is set, the app's
host check would reject a request addressed to 127.0.0.1, so send the first
allowed host as the Host header instead of loosening the check.
"""
import os
import sys
import urllib.request

port = os.environ.get("PORT", "8000")
req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
hosts = [h.strip() for h in os.environ.get("CODEMAP_ALLOWED_HOSTS", "").split(",") if h.strip()]
if hosts:
    req.add_header("Host", hosts[0])
try:
    with urllib.request.urlopen(req, timeout=4) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
