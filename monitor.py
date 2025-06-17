#!/usr/bin/env python3
import os
import time
import threading
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT               = int(os.getenv("PORT", "8000"))
PUSHOVER_USER_KEY  = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS       = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
STOCK_SELECTOR     = os.getenv("STOCK_SELECTOR", "").strip()
CHECK_INTERVAL     = 60             # seconds between cycles
PAGE_LOAD_TIMEOUT  = 15             # max seconds to wait for driver.get()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
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

# ─── PUSHOVER ─────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN):
        logging.warning("Pushover keys missing; skipping notification")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token":PUSHOVER_API_TOKEN,"user":PUSHOVER_USER_KEY,"message":msg},
            timeout=5
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error(f"❌ Pushover error: {e}")

# ─── SINGLE CHECK ──────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ START {url}")
    opts = Options()
    opts.binary_location = os.getenv("CHROME_BIN")
    opts.page_load_strategy = "eager"   # return on DOMContentLoaded
    for f in ("--headless","--no-sandbox","--disable-dev-shm-usage"):
        opts.add_argument(f)

    driver = webdriver.Chrome(service=Service(os.getenv("CHROMEDRIVER_PATH")), options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    try:
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning(f"⚠️ Load timeout; continuing anyway: {url}")

        time.sleep(2)  # let lightweight JS run

        # dismiss cookie/terms if present
        for xp in (
            "//button[normalize-space()='ACCEPT']",
            "//div[contains(@class,'policy_acceptBtn')]"
        ):
            els = driver.find_elements(By.XPATH, xp)
            if els:
                try:
                    els[0].click()
                    logging.info("✓ Accepted overlay")
                    time.sleep(1)
                except:
                    pass
                break

        # look for “add to bag”
        if STOCK_SELECTOR.startswith("//"):
            found = driver.find_elements(By.XPATH, STOCK_SELECTOR)
        else:
            found = driver.find_elements(By.CSS_SELECTOR, STOCK_SELECTOR)

        if found:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)
        else:
            logging.info("   out of stock")

    except Exception as e:
        logging.error(f"Error on {url}: {e}")
    finally:
        driver.quit()
        logging.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS or not STOCK_SELECTOR:
        logging.error("Please set PRODUCT_URLS and STOCK_SELECTOR in env")
        return

    start_health_server()
    logging.info("Starting monitor; first run at top of next minute")

    while True:
        # align to minute
        to_sleep = CHECK_INTERVAL - (time.time() % CHECK_INTERVAL)
        time.sleep(to_sleep)

        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END\n")

if __name__ == "__main__":
    main()
