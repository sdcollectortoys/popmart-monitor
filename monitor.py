#!/usr/bin/env python3
import os
import sys
import time
import logging
import tempfile
import shutil
import requests
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    SessionNotCreatedException,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8000"))
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS", "").split(",") if u.strip()]
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL", "60"))
PUSHOVER_TOKEN  = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER   = os.getenv("PUSHOVER_USER")

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger()

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ALERT ────────────────────────────────────────────────────────────
def send_push(msg: str):
    if not (PUSHOVER_TOKEN and PUSHOVER_USER):
        logger.warning("Missing push credentials; skipping alert")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user":  PUSHOVER_USER,
                "message": msg,
            },
            timeout=10,
        )
        r.raise_for_status()
        logger.info("✔️ Pushover sent")
    except Exception as e:
        logger.error("Pushover error: %s", e)

# ─── CHROME DRIVER SETUP ───────────────────────────────────────────────────────
def make_driver():
    """Attempt up to 3 times to start headless Chrome with a fresh /tmp profile."""
    for attempt in range(1, 4):
        profile_dir = tempfile.mkdtemp(dir="/tmp", prefix="chrome-user-data-")
        opts = Options()
        opts.headless = True
        opts.add_argument(f"--user-data-dir={profile_dir}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")

        try:
            driver = webdriver.Chrome(options=opts)
            driver.set_page_load_timeout(30)
            logger.info(f"Chrome driver started with profile {profile_dir}")
            return driver
        except SessionNotCreatedException as e:
            logger.warning(f"[Attempt {attempt}] Chrome session failed with {profile_dir}: {e}")
            # cleanup and retry
            try:
                shutil.rmtree(profile_dir)
            except Exception:
                pass
            if attempt == 3:
                logger.error("❌ Could not start Chrome after 3 attempts, aborting.")
                sys.exit(1)
        except WebDriverException as e:
            logger.error(f"WebDriverException on startup: {e}")
            sys.exit(1)

# ─── CHECK A SINGLE PRODUCT ────────────────────────────────────────────────────
def check_stock(driver, url: str):
    logger.info(f"→ START {url}")
    try:
        driver.get(url)
    except (TimeoutException, WebDriverException) as e:
        logger.warning(f"⚠️ page-load failed: {e}")

    # If there's a Single-box variant button, click it
    try:
        xpath_var = (
            "//div[contains(@class,'index_sizeInfoItem') "
            "and .//div[normalize-space(text())='Single box']]"
        )
        el = driver.find_element(By.XPATH, xpath_var)
        el.click()
        logger.info("   clicked Single box variant")
        time.sleep(1)
    except Exception:
        pass

    # Look for the exact ADD TO BAG button
    try:
        xpath_btn = (
            "//div[contains(@class,'index_usBtn') "
            "and normalize-space(text())='ADD TO BAG']"
        )
        btns = driver.find_elements(By.XPATH, xpath_btn)
        logger.info(f"   debug: found {len(btns)} matching button(s)")
        if btns:
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
        sys.exit(1)

    start_health_server()
    driver = make_driver()

    # Align to the next interval boundary
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logger.info("🔄 Cycle START")
        for url in PRODUCT_URLS:
            check_stock(driver, url)
        logger.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
