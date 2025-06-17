#!/usr/bin/env python3
import os
import time
import threading
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT               = int(os.getenv("PORT", "8000"))
PUSHOVER_USER_KEY  = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS       = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
# the text fragment to look for in the “Add to bag” button
STOCK_TEXT         = os.getenv("STOCK_TEXT", "add to bag").lower()
# custom UA to pretend we’re a real browser
USER_AGENT         = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.7151.103 Safari/537.36"
)
CHECK_INTERVAL     = 60    # seconds between runs
REQUEST_TIMEOUT    = 10    # seconds per HTTP request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logging.info(f"Health check on port {PORT}")

# ─── PUSHOVER ALERT ────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN):
        logging.warning("Pushover keys missing; skipping")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": PUSHOVER_API_TOKEN, "user": PUSHOVER_USER_KEY, "message": msg},
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error(f"Pushover error: {e}")

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def check_stock(url: str):
    logging.info(f"→ START {url}")
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # find any <button> whose text includes STOCK_TEXT
        found = False
        for btn in soup.find_all("button"):
            if STOCK_TEXT in btn.get_text(strip=True).lower():
                found = True
                break

        if found:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)
        else:
            logging.info("   out of stock")

    except Exception as e:
        logging.error(f"Error on {url}: {e}")
    finally:
        logging.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logging.error("Please set PRODUCT_URLS in env")
        return

    start_health_server()
    logging.info("Starting; first run at top of next minute")

    while True:
        # align to next minute
        to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
        time.sleep(to_sleep)

        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END\n")

if __name__ == "__main__":
    main()
