#!/usr/bin/env python3
import os, time, threading, logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT           = int(os.getenv("PORT", "8000"))
PUSH_KEY       = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN     = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS   = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

FALLBACK_TEXT  = "add to bag"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))
WAIT_BEFORE    = 5   # seconds to let Next.js hydrate
SCRIPT_TIMEOUT = 5   # max seconds for any execute_script call

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
    driver.set_script_timeout(SCRIPT_TIMEOUT)

    try:
        logging.info(f"→ START {url}")
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning("⚠️ Page-load timeout; continuing anyway")

        # allow Next.js hydration
        try:
            WebDriverWait(driver, WAIT_BEFORE).until(
                lambda d: d.execute_script("return !!window.__NEXT_DATA__")
            )
        except TimeoutException:
            logging.warning("⚠️ __NEXT_DATA__ not present in time")

        # ─── PRIMARY: read soldOut boolean ─────────────────────────────────────────
        in_stock = False
        try:
            sold_out = driver.execute_script(
                "return window.__NEXT_DATA__.props.pageProps.product"
                ".skuInfos[0].soldOut"
            )
            in_stock = not sold_out
            logging.info(f"   debug JSON soldOut={sold_out}, inStock={in_stock}")
        except Exception as e:
            logging.warning(f"JSON soldOut lookup failed: {e}")

        # ─── FALLBACK: scan only <button> text ─────────────────────────────────────
        if not in_stock:
            try:
                count = driver.execute_script(f"""
                    return Array.from(document.querySelectorAll('button'))
                      .filter(el => {{
                        const t = (el.textContent||"")
                          .replace(/\\u00A0/g,' ')
                          .toLowerCase();
                        return t.includes("{FALLBACK_TEXT}");
                      }})
                      .length;
                """)
                logging.info(f"   debug JS fallback found {count} button(s) with '{FALLBACK_TEXT}'")
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
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

    while True:
        logging.info("🔄 Cycle START")
        for link in PRODUCT_URLS:
            check_stock(link)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
