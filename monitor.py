#!/usr/bin/env python3
import os
import time
import threading
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from concurrent.futures import ThreadPoolExecutor

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# ─── Configuration ─────────────────────────────────────────────────────────────
PORT               = int(os.getenv("PORT",             "8000"))
PUSHOVER_USER_KEY  = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")

# Comma-separated list of PopMart product URLs
PRODUCT_URLS = [
    url.strip() for url in
    os.getenv("PRODUCT_URLS", "").split(",") if url.strip()
]

# Can be a CSS selector (default) or an XPath (if it starts with "//")
STOCK_SELECTOR = os.getenv("STOCK_SELECTOR", "").strip()

# Number of seconds between checks (we’ll align to minute)
CHECK_INTERVAL = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── Health-check server ──────────────────────────────────────────────────────
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info(f"Health check listening on port {PORT}")

# ─── Pushover ──────────────────────────────────────────────────────────────────
def send_pushover(message: str):
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        logging.warning("Pushover keys missing; skipping notification")
        return

    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user":  PUSHOVER_USER_KEY,
        "message": message
    }
    try:
        resp = requests.post("https://api.pushover.net/1/messages.json", data=payload)
        resp.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error(f"❌ Pushover error: {e}")

# ─── Single-URL check ─────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ Checking {url}")
    chrome_opts = Options()
    chrome_opts.binary_location = os.getenv("CHROME_BIN")
    for arg in ("--headless", "--no-sandbox", "--disable-dev-shm-usage"):
        chrome_opts.add_argument(arg)

    service = Service(os.getenv("CHROMEDRIVER_PATH"))
    driver  = webdriver.Chrome(service=service, options=chrome_opts)

    try:
        driver.get(url)
        time.sleep(5)  # allow JS to load
        if STOCK_SELECTOR.startswith("//"):
            elems = driver.find_elements(By.XPATH, STOCK_SELECTOR)
        else:
            elems = driver.find_elements(By.CSS_SELECTOR, STOCK_SELECTOR)

        if elems:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)
        else:
            logging.info("   out of stock")
    except Exception as e:
        logging.error(f"Error on {url}: {e}")
    finally:
        driver.quit()

# ─── Main loop ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS or not STOCK_SELECTOR:
        logging.error("Please set PRODUCT_URLS and STOCK_SELECTOR in env")
        return

    start_health_server()
    logging.info("Starting monitor; first run at top of next minute")

    while True:
        # sleep until the top of the next minute
        now = time.time()
        to_sleep = CHECK_INTERVAL - (now % CHECK_INTERVAL)
        time.sleep(to_sleep)

        logging.info("🔄 Beginning check cycle")
        with ThreadPoolExecutor(max_workers=len(PRODUCT_URLS)) as pool:
            pool.map(check_stock, PRODUCT_URLS)

if __name__ == "__main__":
    main()
