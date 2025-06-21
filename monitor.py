#!/usr/bin/env python3
import os
import sys
import time
import logging
import requests
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT           = int(os.getenv("PORT", "8000"))
PRODUCT_URLS   = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER  = os.getenv("PUSHOVER_USER")

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger()

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ALERT ────────────────────────────────────────────────────────────
def send_push(msg: str):
    if not (PUSHOVER_TOKEN and PUSHOVER_USER):
        logger.warning("Missing Pushover credentials; skipping alert")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": PUSHOVER_TOKEN, "user": PUSHOVER_USER, "message": msg},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("✔️ Pushover sent")
    except Exception as e:
        logger.error(f"Pushover error: {e}")

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
def check_stock(url: str):
    logger.info(f"→ START {url}")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"⚠️ fetch failed: {e}")
        logger.info(f"← END   {url}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for the single-box selector and click it—**not** needed: single is default.
    # Now scan for the exact ADD TO BAG div
    buttons = soup.find_all(
        "div",
        class_=lambda c: c and "index_usBtn" in c,
        string=lambda txt: txt and txt.strip().upper() == "ADD TO BAG"
    )
    found = len(buttons)
    logger.info(f"   debug: found {found} ADD TO BAG button(s)")
    if found:
        ts  = datetime.now().strftime("%H:%M")
        msg = f"[{ts}] 🚨 IN STOCK → {url}"
        logger.info(msg)
        send_push(msg)
    else:
        logger.info("   out of stock")

    logger.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logger.error("No PRODUCT_URLS set in env; aborting")
        sys.exit(1)

    start_health_server()

    # drift-proof sleep until next interval
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logger.info("🔄 Cycle START")
        for url in PRODUCT_URLS:
            check_stock(url)
        logger.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
