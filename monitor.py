# monitor.py
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

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT         = int(os.getenv("PORT", "8000"))
PUSH_KEY     = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN   = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]

# always use this default XPath
STOCK_SELECTOR = (
    "//*[contains(translate(normalize-space(.),"
    " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
    " 'add to bag')]"
)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL","60"))
PAGE_TIMEOUT   = int(os.getenv("PAGE_TIMEOUT","15"))
WAIT_BEFORE    = 3

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
        logging.warning("Missing Pushover creds; skipping alert")
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

# ─── SINGLE CHECK ──────────────────────────────────────────────────────────────
def check_stock(url: str):
    # confirm this code actually ran
    logging.info("🚨 DEBUG MODE: check_stock() invoked")
    logging.info(f"🚨 DEBUG MODE: STOCK_SELECTOR = {STOCK_SELECTOR!r}")

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
            logging.warning("⚠️ Page‐load timeout; continuing")

        time.sleep(WAIT_BEFORE)

        # safe overlay-click
        try:
            ov = driver.find_elements(By.XPATH, "//div[contains(@class,'policy_acceptBtn')]")
            if ov:
                ov[0].click()
                logging.info("✓ Accepted overlay")
                time.sleep(1)
        except Exception as e:
            logging.warning(f"Overlay-click failed, continuing: {e}")

        # ── DEBUG #1: raw HTML check ───────────────────────────────────
        raw_html = ""
        try:
            raw_html = driver.page_source.replace("\u00A0"," ")
        except (TimeoutException, WebDriverException) as e:
            logging.warning(f"raw page_source timed out or failed: {e}")
            try:
                # fallback via JS
                raw_html = driver.execute_script(
                    "return document.documentElement.outerHTML"
                ).replace("\u00A0"," ")
                logging.info("   debug1: fallback outerHTML succeeded")
            except Exception as je:
                logging.warning(f"fallback outerHTML also failed: {je}")

        low = raw_html.lower()
        found_sub = "add to bag" in low
        logging.info(f"   debug1: raw HTML contains 'add to bag'? {found_sub}")
        if found_sub:
            idx = low.find("add to bag")
            snippet = raw_html[max(0, idx-80):idx+80].replace("\n"," ")
            logging.info(f"   debug1 snippet: …{snippet}…")

        # ── DEBUG #2: XPath matches ───────────────────────────────────
        matches = driver.find_elements(By.XPATH, STOCK_SELECTOR)
        logging.info(f"   debug2: STOCK_SELECTOR matched {len(matches)} element(s)")
        for el in matches:
            logging.info(f"      → tag={el.tag_name!r}, text={el.text!r}")

        # ── ALERT DECISION ───────────────────────────────────────────
        if matches:
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
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__ == "__main__":
    main()
