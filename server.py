"""
Serves the solv-skills static files and refreshes observatory data daily.
"""

import os
import threading
import time
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = int(os.getenv("PORT", 8080))
ROOT = Path(__file__).parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/ines/ClearPay_Collection_Metrics_NextCare_Discharged.html")
            self.end_headers()
        else:
            super().do_GET()

    def log_message(self, format, *args):
        print(f"[{self.date_time_string()}] {format % args}", flush=True)


EASTERN = ZoneInfo("America/New_York")
REFRESH_HOUR = 3  # 3 AM ET


def next_refresh_time():
    now = datetime.now(EASTERN)
    target = now.replace(hour=REFRESH_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def refresh_loop():
    # Refresh immediately on startup, then every day at 3 AM ET
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

        target = next_refresh_time()
        sleep_secs = (target - datetime.now(EASTERN)).total_seconds()
        print(f"[refresh] Next refresh at {target.strftime('%Y-%m-%d %H:%M %Z')} ({sleep_secs/3600:.1f}h from now)", flush=True)
        time.sleep(sleep_secs)


if __name__ == "__main__":
    # Start background refresh thread
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    print(f"Serving on port {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
