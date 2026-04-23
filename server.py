"""
Serves the solv-skills static files and refreshes observatory data daily.
"""

import os
import threading
import time
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = int(os.getenv("PORT", 8080))
ROOT = Path(__file__).parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        print(f"[{self.date_time_string()}] {format % args}", flush=True)


def refresh_loop():
    # Refresh immediately on startup, then every 24 hours
    while True:
        try:
            print("[refresh] Running observatory data refresh...", flush=True)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "generate_observatory.py")],
                capture_output=True, text=True, timeout=300
            )
            print(result.stdout, flush=True)
            if result.returncode != 0:
                print(f"[refresh] ERROR: {result.stderr}", flush=True)
            else:
                print("[refresh] Done.", flush=True)
        except Exception as e:
            print(f"[refresh] Failed: {e}", flush=True)
        time.sleep(86400)  # 24 hours


if __name__ == "__main__":
    # Start background refresh thread
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    print(f"Serving on port {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
