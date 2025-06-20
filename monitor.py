#!/usr/bin/env python3
import os, time, threading, logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT          = int(os.getenv("PORT", "8000"))
PUSH_KEY      = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN    = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS  = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

# Fallback XPath (in case JSON lookup fails)
XPATH_FALLBACK = (
    "//*[contains(translate(normalize-space(.),"
    " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
    " 'add to bag')]"
)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))
WAIT_BEFORE    = 2   # give Next.js a moment to hydrate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def start_health_server():
    srv = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logging.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Missing Pushover creds; skipping")
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

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info("🚨 DEBUG MODE: check_stock() invoked")

    # set up headless Chrome
    opts = Options()
    for flag in ("--headless","--no-sandbox","--disable-dev-shm-usage"):
        opts.add_argument(flag)
    opts.page_load_strategy = "eager"
    service = Service(os.getenv("CHROMEDRIVER_PATH","/usr/bin/chromedriver"))
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)

    try:
        logging.info(f"→ START {url}")
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning("⚠️ Page-load timeout; continuing anyway")

        # wait for Next.js data to hydrate
        WebDriverWait(driver, WAIT_BEFORE).until(
            lambda d: d.execute_script("return !!window.__NEXT_DATA__")
        )

        # retrieve the JSON blob
        data = driver.execute_script("return window.__NEXT_DATA__.props.pageProps.product")
        # most Next pages have skuInfos[0].soldOut boolean
        sold_out = data.get("skuInfos", [{}])[0].get("soldOut", True)
        in_stock = not sold_out

        logging.info(f"   debug JSON soldOut={sold_out}, inStock={in_stock}")

        # FALLBACK: if JSON says soldOut but XPATH_FALLBACK finds add-to-bag, override
        if not in_stock:
            if driver.find_elements(By.XPATH, XPATH_FALLBACK):
                logging.info("   debug: fallback XPath found add-to-bag → overriding JSON")
                in_stock = True

        if in_stock:
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)
        else:
            logging.info("   out of stock")

    except Exception as e:
        logging.exception(f"Error on {url}: {e}")
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
