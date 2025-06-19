#!/usr/bin/env python3
import os, time, threading, logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8000"))
PUSH_KEY        = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN      = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

# match ANY element containing “add to bag” (case-insensitive)
STOCK_SELECTOR = os.getenv("STOCK_SELECTOR",
    "//*[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
    " 'add to bag')]"
)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))  # seconds between cycles
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))    # max seconds to load page
WAIT_TIMEOUT   = int(os.getenv("WAIT_TIMEOUT","10"))    # seconds to wait for button

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
        logging.warning("Pushover keys missing; skipping")
        return
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token":PUSH_TOKEN,"user":PUSH_KEY,"message":msg},
            timeout=10
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

# ─── STOCK CHECK ───────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ START {url}")

    # set up headless Chrome
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.page_load_strategy = "eager"

    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)

    try:
        # load page
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning(f"⚠️ Page load timed out; proceeding anyway: {url}")

        # dismiss any overlay
        els = driver.find_elements(By.XPATH, "//div[contains(@class,'policy_acceptBtn')]")
        if els:
            els[0].click()
            logging.info("✓ Accepted T&C overlay")
            time.sleep(1)

        # now wait up to WAIT_TIMEOUT for an “add to bag” match
        try:
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, STOCK_SELECTOR))
            )
            # if we get here, element is present
            msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
            logging.info(msg)
            send_pushover(msg)

        except TimeoutException:
            # not found within WAIT_TIMEOUT
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
    # align to next minute
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        # sleep until top of next minute
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
