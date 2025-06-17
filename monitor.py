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
from selenium.common.exceptions import TimeoutException

# ─── Configuration ─────────────────────────────────────────────────────────────
PORT               = int(os.getenv("PORT",             "8000"))
PUSHOVER_USER_KEY  = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")

# Comma-separated PopMart URLs
PRODUCT_URLS = [
    url.strip() for url in
    os.getenv("PRODUCT_URLS", "").split(",") if url.strip()
]

# CSS selector or XPath for "add to bag"
STOCK_SELECTOR = os.getenv("STOCK_SELECTOR", "").strip()

# Seconds between cycles
CHECK_INTERVAL = 60

# Maximum time to wait for page load (in seconds)
PAGE_LOAD_TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── Health-check server ────────────────────────────────────────────────────────
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
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data=payload,
            timeout=10
        )
        resp.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error(f"❌ Pushover error: {e}")

# ─── Single-URL check ───────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ Checking {url}")
    chrome_opts = Options()
    chrome_opts.binary_location = os.getenv("CHROME_BIN")
    # return once DOM is interactive
    chrome_opts.set_capability("pageLoadStrategy", "eager")
    for arg in ("--headless", "--no-sandbox", "--disable-dev-shm-usage"):
        chrome_opts.add_argument(arg)

    service = Service(os.getenv("CHROMEDRIVER_PATH"))
    driver = webdriver.Chrome(service=service, options=chrome_opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    try:
        # try to load; if it times out, continue anyway
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning(f"⚠️ Timeout loading page; proceeding: {url}")

        # give a moment for JS overlays
        time.sleep(5)

        # ── Dismiss terms/cookies overlay if present
        for xpath in (
            "//button[normalize-space()='ACCEPT']",
            "//div[contains(@class,'policy_acceptBtn')]"
        ):
            els = driver.find_elements(By.XPATH, xpath)
            if els:
                try:
                    els[0].click()
                    logging.info("✓ Accepted terms overlay")
                    time.sleep(2)
                except Exception:
                    pass
                break

        # ── Check for “add to bag” button
        if STOCK_SELECTOR.startswith("//"):
            matches = driver.find_elements(By.XPATH, STOCK_SELECTOR)
        else:
            matches = driver.find_elements(By.CSS_SELECTOR, STOCK_SELECTOR)

        if matches:
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
        # align with top of minute
        now = time.time()
        to_sleep = CHECK_INTERVAL - (now % CHECK_INTERVAL)
        time.sleep(to_sleep)

        logging.info("🔄 Beginning check cycle")
        with ThreadPoolExecutor(max_workers=len(PRODUCT_URLS)) as pool:
            pool.map(check_stock, PRODUCT_URLS)

if __name__ == "__main__":
    main()
