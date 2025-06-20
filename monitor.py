#!/usr/bin/env python3
import os
import time
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT             = int(os.getenv("PORT", "8000"))
PUSH_KEY         = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN       = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS     = [
    u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()
]
CHECK_INTERVAL   = int(os.getenv("CHECK_INTERVAL", "60"))
REQUEST_TIMEOUT  = 10  # seconds

# Substrings to look for
IN_STOCK_MARKER    = "add to bag"
OUT_OF_STOCK_MARKER = "notify me when available"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; stock-monitor/1.0)"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Missing Pushover creds; skipping alert")
        return
    try:
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": PUSH_TOKEN, "user": PUSH_KEY, "message": msg},
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ START {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logging.error("HTTP error fetching %s: %s", url, e)
        return

    txt = r.text.lower()

    has_add    = IN_STOCK_MARKER in txt
    has_notify = OUT_OF_STOCK_MARKER in txt

    logging.info(f"   debug: found '{IN_STOCK_MARKER}'? {has_add}, "
                 f"found '{OUT_OF_STOCK_MARKER}'? {has_notify}")

    in_stock = False
    if has_add and not has_notify:
        in_stock = True
    elif has_add and has_notify:
        # both present: page may include both in different sections; trust in-stock
        in_stock = True
    else:
        in_stock = False

    if in_stock:
        msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
        logging.info(msg)
        send_pushover(msg)
    else:
        logging.info("   out of stock")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logging.error("No PRODUCT_URLS set in env")
        return

    start_health_server()
    # align to next interval boundary
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
