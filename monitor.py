#!/usr/bin/env python3
import os
import sys
import time
import re
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ── CONFIG ────────────────────────────────────────────────────────────

# List your SPU IDs here or override via SPU_IDS="878,890,2155,2879,2492"
if os.environ.get("SPU_IDS"):
    SPUS = [s.strip() for s in os.environ["SPU_IDS"].split(",") if s.strip()]
else:
    SPUS = ["878", "890", "2155", "2879", "2492"]

# How often to poll (seconds)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

# Health‐check port (Render will inject $PORT)
PORT = int(os.environ.get("PORT", "5000"))

# Pushover credentials
PUSH_APP_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
PUSH_USER_KEY  = os.environ.get("PUSHOVER_USER_KEY")

# Pushover endpoint
PUSH_URL = "https://api.pushover.net/1/messages.json"

# ── LOGGING SETUP ───────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── HEALTH SERVER ──────────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server running on 0.0.0.0:{PORT}/health")

# ── STOCK FETCHER ──────────────────────────────────────────────────────

def fetch_stock(spu_id: str) -> bool:
    """
    Returns True if any SKU for spu_id has onlineStock > 0.
    """
    url = f"https://www.popmart.com/us/products/{spu_id}"
    try:
        resp = requests.get(url, timeout=15)
    except requests.RequestException as e:
        logger.error(f"[SPU {spu_id}] network error: {e}")
        return False

    if resp.status_code != 200:
        logger.error(f"[SPU {spu_id}] unexpected HTTP {resp.status_code}")
        return False

    # extract the JSON blob Next.js injects
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        flags=re.DOTALL
    )
    if not m:
        logger.error(f"[SPU {spu_id}] __NEXT_DATA__ not found in page")
        return False

    try:
        data = json.loads(m.group(1))
        pd = data["props"]["pageProps"]["productDetails"]
        for sku in pd.get("skus", []):
            if sku.get("stock", {}).get("onlineStock", 0) > 0:
                return True
    except Exception as e:
        logger.error(f"[SPU {spu_id}] error parsing JSON: {e}")

    return False

# ── PUSHOVER NOTIFIER ─────────────────────────────────────────────────

def send_push(message: str):
    if not PUSH_APP_TOKEN or not PUSH_USER_KEY:
        logger.warning("Pushover credentials missing; skipping notification")
        return
    try:
        resp = requests.post(PUSH_URL, data={
            "token": PUSH_APP_TOKEN,
            "user":  PUSH_USER_KEY,
            "message": message,
        }, timeout=10)
        resp.raise_for_status()
        logger.info("Pushover notification sent")
    except Exception as e:
        logger.error(f"Pushover error: {e}")

# ── MAIN LOOP ─────────────────────────────────────────────────────────

def main():
    if not SPUS:
        logger.error("No SPU IDs configured. Set SPU_IDS env var or update the script.")
        sys.exit(1)

    # start the health‐check endpoint
    start_health_server()

    # keep track of last seen stock state
    last_status = {spu: False for spu in SPUS}
    logger.info(f"Monitoring SPUs for restock: {SPUS} (interval: {CHECK_INTERVAL}s)")

    try:
        while True:
            for spu in SPUS:
                in_stock = fetch_stock(spu)
                if in_stock and not last_status[spu]:
                    msg = f"🎉 SPU {spu} is NOW IN STOCK! → https://www.popmart.com/us/products/{spu}"
                    logger.info(msg)
                    send_push(msg)
                last_status[spu] = in_stock
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Interrupted—shutting down.")
        sys.exit(0)

if __name__ == "__main__":
    main()
