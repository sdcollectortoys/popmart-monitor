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
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT          = int(os.getenv("PORT", "8000"))
PUSH_KEY      = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN    = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS  = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

# FALLBACK: JS snippet will look for this substring in textContent
FALLBACK_TEXT = "add to bag"

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))
WAIT_BEFORE    = 3  # seconds to wait for Next.js hydration

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
    srv = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logging.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Missing Pushover creds; skipping alert")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token":PUSH_TOKEN, "user":PUSH_KEY, "message":msg},
            timeout=10
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

# ─── SINGLE CHECK ──────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info("🚨 DEBUG MODE: check_stock() invoked")

    opts = Options()
    for flag in ("--headless", "--no-sandbox", "--disable-dev-shm-usage"):
        opts.add_argument(flag)
    opts.page_load_strategy = "eager"

    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)

    try:
        logging.info(f"→ START {url}")
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning("⚠️ Page-load timeout; continuing anyway")

        # give Next.js data a moment to appear
        try:
            WebDriverWait(driver, WAIT_BEFORE).until(
                lambda d: d.execute_script("return !!window.__NEXT_DATA__")
            )
        except TimeoutException:
            logging.warning("⚠️ NEXT_DATA did not load in time; will fallback to JS scan")

        # ─── PRIMARY CHECK: JSON from Next.js ───────────────────────────────────
        in_stock = False
        try:
            data = driver.execute_script("return window.__NEXT_DATA__.props.pageProps.product")
            sold_out = data.get("skuInfos", [{}])[0].get("soldOut", True)
            in_stock = not sold_out
            logging.info(f"   debug JSON soldOut={sold_out}, inStock={in_stock}")
        except Exception as e:
            logging.warning(f"JSON lookup failed: {e}")

        # ─── FALLBACK CHECK: JS text scan ────────────────────────────────────────
        if not in_stock:
            try:
                count = driver.execute_script(f"""
                    return Array.from(document.querySelectorAll('*'))
                      .filter(el => el.textContent && 
                                     el.textContent.toLowerCase().includes('{FALLBACK_TEXT}'))
                      .length;
                """)
                logging.info(f"   debug JS fallback found {count} elements containing '{FALLBACK_TEXT}'")
                in_stock = (count > 0)
            except Exception as e:
                logging.warning(f"JS fallback scan failed: {e}")

        # ─── ALERT DECISION ─────────────────────────────────────────────────────
        if in_stock:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)
        else:
            logging.info("   out of stock")

    except Exception:
        logging.exception(f"Error on {url}")
    finally:
        driver.quit()
        logging.info(f"← END   {url}")

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    if not PRODUCT_URLS:
        logging.error("No PRODUCT_URLS set in env")
        return

    start_health_server()
    # align to next minute boundary
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
