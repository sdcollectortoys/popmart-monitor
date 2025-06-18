# monitor.py
#!/usr/bin/env python3
import os, time, threading, logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from bs4 import BeautifulSoup

PORT            = int(os.getenv("PORT", "8000"))
PUSH_KEY        = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN      = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]
STOCK_TEXT      = os.getenv("STOCK_TEXT","add to bag").lower()
USER_AGENT      = os.getenv("USER_AGENT","Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/…")
CHECK_INTERVAL  = 60
REQUEST_TIMEOUT = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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

def send_pushover(msg):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Missing Pushover keys; skipping")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token":PUSH_TOKEN,"user":PUSH_KEY,"message":msg},
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def check_stock(url):
    logging.info("→ START %s", url)
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT); r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        found = any(
            STOCK_TEXT in btn.get_text(strip=True).lower()
            for btn in soup.find_all("button")
        )
        if found:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg); send_pushover(msg)
        else:
            logging.info("   out of stock")
    except Exception:
        logging.exception("Error checking %s", url)
    finally:
        logging.info("← END   %s", url)

def main():
    if not PRODUCT_URLS:
        logging.error("No PRODUCT_URLS set"); return
    start_health_server()
    # align to next minute
    to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
    time.sleep(to_sleep)
    while True:
        try:
            logging.info("🔄 Cycle START")
            for u in PRODUCT_URLS: check_stock(u)
            logging.info("✅ Cycle END")
        except Exception:
            logging.exception("💥 Uncaught error in cycle")
        finally:
            to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
            time.sleep(to_sleep)

if __name__ == "__main__":
    main()
