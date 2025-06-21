#!/usr/bin/env python3
import os
import time
import logging
import requests
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8000"))
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL", "60"))
PUSHOVER_TOKEN  = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER   = os.getenv("PUSHOVER_USER")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger()

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def start_health_server():
    srv = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logger.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_push(msg: str):
    if not (PUSHOVER_TOKEN and PUSHOVER_USER):
        logger.warning("Missing push credentials; skipping alert")
        return
    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data={
            "token":   PUSHOVER_TOKEN,
            "user":    PUSHOVER_USER,
            "message": msg
        }, timeout=10)
        r.raise_for_status()
        logger.info("✔️ Pushover sent")
    except Exception as e:
        logger.error("Pushover error: %s", e)

# ─── BROWSER SETUP ─────────────────────────────────────────────────────────────
def make_driver():
    opts = Options()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver

# ─── CHECK ONE PRODUCT ─────────────────────────────────────────────────────────
def check_stock(driver, url: str):
    logger.info(f"→ START {url}")
    try:
        driver.get(url)
    except (TimeoutException, WebDriverException) as e:
        logger.warning(f"⚠️ page-load failed: {e}")

    # 1) Click the “Single box” wrapper (if present)
    try:
        variant_xpath = (
            "//div[contains(@class,'index_sizeInfoItem') "
            "and .//div[normalize-space(text())='Single box']]"
        )
        wrapper = driver.find_element(By.XPATH, variant_xpath)
        wrapper.click()
        logger.info("   clicked Single box")
        time.sleep(1)
    except Exception as e:
        logger.debug(f"   variant click skipped: {e}")

    # 2) Look *only* for the exact “ADD TO BAG” button
    try:
        stock_xpath = (
            "//div[contains(@class,'index_usBtn') "
            "and contains(normalize-space(.),'ADD TO BAG')]"
        )
        buttons = driver.find_elements(By.XPATH, stock_xpath)
        logger.info(f"   debug: found {len(buttons)} matching button(s)")
        if buttons:
            ts = datetime.now().strftime("%H:%M")
            msg = f"[{ts}] 🚨 IN STOCK → {url}"
            logger.info(msg)
            send_push(msg)
        else:
            logger.info("   out of stock")
    except Exception as e:
        logger.error(f"   button scan failed: {e}")

    logger.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logger.error("No PRODUCT_URLS set in env; aborting")
        return

    start_health_server()
    driver = make_driver()

    # align to the minute
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logger.info("🔄 Cycle START")
        for url in PRODUCT_URLS:
            check_stock(driver, url)
        logger.info("✅ Cycle END")
        # sleep until next cycle
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
