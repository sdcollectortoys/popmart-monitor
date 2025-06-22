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

# SPU IDs to monitor (override with SPU_IDS="878,890,2155,2879,2492")
if os.environ.get("SPU_IDS"):
    SPUS = [s.strip() for s in os.environ["SPU_IDS"].split(",") if s.strip()]
else:
    SPUS = ["878", "890", "2155", "2879", "2492"]

# Poll interval (seconds)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

# HTTP health‐check port (Render supplies $PORT)
PORT = int(os.environ.get("PORT", "5000"))

# Pushover credentials (must match your env var names)
PUSH_APP_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
PUSH_USER_KEY  = os.environ.get("PUSHOVER_USER_KEY")
PUSH_URL       = "https://api.pushover.net/1/messages.json"

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
    logger.info(f"Health server listening on 0.0.0.0:{PORT}/health")

# ── STOCK FETCHER ──────────────────────────────────────────────────────

def fetch_stock(spu_id: str) -> bool:
    """
    Scrape the public product page and look for any SKU with onlineStock > 0.
    Returns True if in stock, False otherwise.
    """
    url = f"https://www.popmart.com/us/products/{spu_id}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"[SPU {spu_id}] network error: {e}")
        return False

    # Extract the Next.js __NEXT_DATA__ JSON blob
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text, flags=re.DOTALL
    )
    if not m:
        logger.error(f"[SPU {spu_id}] __NEXT_DATA__ not found")
        return False

    try:
        blob = json.loads(m.group(1))
        pd    = blob["props"]["pageProps"]["productDetails"]
        for sku in pd.get("skus", []):
            if sku.get("stock", {}).get("onlineStock", 0) > 0:
                return True
    except Exception as e:
        logger.error(f"[SPU {spu_id}] error parsing JSON: {e}")
        return False

    return False

# ── PUSHOVER NOTIFIER ─────────────────────────────────────────────────

def send_push(message: str):
    if not PUSH_APP_TOKEN or not PUSH_USER_KEY:
        logger.warning("Missing PUSHOVER_API_TOKEN or PUSHOVER_USER_KEY → skipping push")
        return

    try:
        resp = requests.post(PUSH_URL, data={
            "token":   PUSH_APP_TOKEN,
            "user":    PUSH_USER_KEY,
            "message": message
        }, timeout=10)
        resp.raise_for_status()
        logger.info("Pushover notification sent")
    except Exception as e:
        logger.error(f"Pushover error: {e}")

# ── MAIN LOOP ─────────────────────────────────────────────────────────

def main():
    if not SPUS:
        logger.error("No SPU IDs configured. Export SPU_IDS or edit the script.")
        sys.exit(1)

    start_health_server()

    # Track last-known in-stock status
    last_seen = {spu: False for spu in SPUS}
    logger.info(f"Starting monitor for SPUs {SPUS} every {CHECK_INTERVAL}s")

    try:
        while True:
            for spu in SPUS:
                now_in = fetch_stock(spu)
                # on transition False→True send alert
                if now_in and not last_seen[spu]:
                    link = f"https://www.popmart.com/us/products/{spu}"
                    msg  = f"🎉 SPU {spu} now IN STOCK! → {link}"
                    logger.info(msg)
                    send_push(msg)
                last_seen[spu] = now_in
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Interrupted, exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
