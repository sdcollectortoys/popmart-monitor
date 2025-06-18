# monitor.py
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
PORT            = int(os.getenv("PORT",             "8000"))
PUSH_KEY        = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN      = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
STOCK_TEXT      = os.getenv("STOCK_TEXT",          "add to bag").lower()
USER_AGENT      = os.getenv("USER_AGENT",          
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.7151.103 Safari/537.36"
)
CHECK_INTERVAL  = 60   # seconds between cycles
REQUEST_TIMEOUT = 10   # HTTP request timeout

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
    logging.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Pushover keys missing; skipping notification")
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
        logging.error(f"Pushover error: {e}")

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def check_stock(url: str):
    logging.info(f"→ START {url}")
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # look for any <button> containing our STOCK_TEXT
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

    except Exception:
        logging.exception(f"Error checking {url}")
    finally:
        logging.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logging.error("Please set PRODUCT_URLS in env")
        return

    start_health_server()
    logging.info("Starting monitor; first run at top of next minute")

    # align to the next minute
    to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
    time.sleep(to_sleep)

    while True:
        try:
            logging.info("🔄 Cycle START")
            for u in PRODUCT_URLS:
                check_stock(u)
            logging.info("✅ Cycle END")
        except Exception:
            logging.exception("💥 Uncaught error in cycle")
        finally:
            to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
            time.sleep(to_sleep)

if __name__ == "__main__":
    main()
