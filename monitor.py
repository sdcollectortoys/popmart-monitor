#!/usr/bin/env python3
import os, time, threading, logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT           = int(os.getenv("PORT", "8000"))
PUSH_KEY       = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN     = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS   = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))
WAIT_AFTER     = 2  # seconds to wait after each click

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─── HEALTH CHECK ──────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def start_health_server():
    server = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
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

# ─── SINGLE CHECK ───────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info("🚨 DEBUG MODE: check_stock() invoked")

    # headless Chrome
    opts = Options()
    for f in ("--headless","--no-sandbox","--disable-dev-shm-usage"):
        opts.add_argument(f)
    opts.page_load_strategy = "eager"
    serv = Service(os.getenv("CHROMEDRIVER_PATH","/usr/bin/chromedriver"))
    driver = webdriver.Chrome(service=serv, options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)

    try:
        logging.info(f"→ START {url}")
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning("⚠️ page-load timeout; continuing")

        time.sleep(WAIT_AFTER)

        # dismiss T&C overlay
        try:
            ov = driver.find_element(By.XPATH, "//div[contains(@class,'policy_acceptBtn')]")
            ov.click()
            logging.info("✓ Accepted T&C overlay")
            time.sleep(WAIT_AFTER)
        except Exception:
            pass

        # select "Single Box" if present
        try:
            btns = driver.find_elements(By.XPATH,
                "//button[contains(normalize-space(.),'Single Box')]"
            )
            if btns:
                btns[0].click()
                logging.info("✓ Selected Single Box variant")
                time.sleep(WAIT_AFTER)
        except Exception as e:
            logging.warning(f"Variant click failed: {e}")

        # scan only the small set of <button> tags for "Add to Bag"
        in_stock = False
        try:
            for b in driver.find_elements(By.TAG_NAME, "button"):
                txt = b.text.strip().lower()
                if "add to bag" in txt:
                    in_stock = True
                    logging.info(f"   debug: matched button text = {b.text!r}")
                    break
            logging.info(f"   debug: in_stock={in_stock}")
        except Exception as e:
            logging.warning(f"Button scan failed: {e}")

        # alert
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
        logging.error("No PRODUCT_URLS set in env"); return

    start_health_server()
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__=="__main__":
    main()
