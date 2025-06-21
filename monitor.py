#!/usr/bin/env python3
import os
import sys
import time
import uuid
import signal
import sqlite3
import threading
import random
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---- Health-check HTTP server ----
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server(port=10000):
    srv = HTTPServer(("", port), HealthHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

# ---- Pushover alert ----
PUSH_APP_TOKEN = os.environ["PUSHOVER_APP_TOKEN"]
PUSH_USER_KEY  = os.environ["PUSHOVER_USER_KEY"]
def send_pushover(message: str):
    resp = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": PUSH_APP_TOKEN, "user": PUSH_USER_KEY, "message": message},
        timeout=10,
    )
    resp.raise_for_status()

# ---- SQLite state persistence ----
DB_PATH = "state.db"
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS stock_state (
        url        TEXT PRIMARY KEY,
        last_state TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL
      );
    """)
    conn.commit()
    return conn

# ---- Selenium WebDriver factory with stealth ----
def make_driver():
    # Enable performance logs (unused now, but harmless)
    caps = DesiredCapabilities.CHROME.copy()
    caps['goog:loggingPrefs'] = {'performance': 'ALL'}

    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument("--headless=new")  # use new headless mode
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")

    # anti-automation flags
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # disable images for speed
    opts.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2
    })

    # random-ish UA
    ua = (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{random.randint(100,116)}.0.0.0 Safari/537.36"
    )
    opts.add_argument(f"--user-agent={ua}")

    # per-run user-data-dir
    profile = f"/tmp/stockmon-{uuid.uuid4()}"
    opts.add_argument(f"--user-data-dir={profile}")

    driver = webdriver.Chrome(desired_capabilities=caps, options=opts)

    # Inject stealth script so navigator.webdriver is undefined
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        """
    })

    driver.set_page_load_timeout(20)
    return driver

# ---- Overlay acceptance ----
def accept_overlays(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[normalize-space(text())='I Agree'"
                " or normalize-space(text())='Accept'"
                " or contains(., 'Continue')]"
            ))
        )
        btn.click()
        time.sleep(0.5)
    except TimeoutException:
        pass

# ---- Stock check via text search ----
def check_stock(driver, url: str) -> str:
    driver.get(url)
    accept_overlays(driver)

    # give JS time to render the buy-button
    time.sleep(2)

    # find any element whose text contains "ADD TO BAG" (case-insensitive)
    xpath_in = (
        "//*[contains(translate(normalize-space(.),"
        " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        " 'abcdefghijklmnopqrstuvwxyz'), 'add to bag')]"
    )
    elems = driver.find_elements(By.XPATH, xpath_in)
    print(f"debug: found {len(elems)} ADD TO BAG element(s)")
    return "in" if elems else "out"

def sleep_until_top_of_minute():
    now = time.time()
    delay = 60 - (now % 60)
    time.sleep(delay + random.uniform(0, 1))

# ---- Main service ----
def main():
    urls = [u.strip() for u in os.environ.get("PRODUCT_URLS", "").split(",") if u.strip()]
    if not urls:
        print("No PRODUCT_URLS configured; exiting.")
        sys.exit(1)

    conn = init_db()
    cur = conn.cursor()
    driver = make_driver()
    health_srv = start_health_server()

    def clean_exit(*_):
        print("Shutting down...")
        try: driver.quit()
        except: pass
        try: conn.close()
        except: pass
        try: health_srv.shutdown()
        except: pass
        sys.exit(0)

    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)

    print("Monitor started. Polling every minute.")
    while True:
        sleep_until_top_of_minute()
        for url in urls:
            state = None
            for attempt in range(1, 4):
                try:
                    state = check_stock(driver, url)
                    break
                except WebDriverException as e:
                    print(f"[Attempt {attempt}] error checking {url}: {e}", file=sys.stderr)
                    time.sleep(attempt)
            if state is None:
                print(f"All attempts failed for {url}", file=sys.stderr)
                continue

            cur.execute("SELECT last_state FROM stock_state WHERE url = ?", (url,))
            row = cur.fetchone()
            old = row[0] if row else "out"
            if old == "out" and state == "in":
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {url} → IN STOCK!")
                try:
                    send_pushover(f"🔥 In stock: {url}")
                except Exception as e:
                    print(f"Pushover error: {e}", file=sys.stderr)

            if not row:
                cur.execute(
                    "INSERT INTO stock_state(url,last_state,updated_at) "
                    "VALUES(?,?,CURRENT_TIMESTAMP)",
                    (url, state)
                )
            else:
                cur.execute(
                    "UPDATE stock_state "
                    "SET last_state=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE url=?",
                    (state, url)
                )
            conn.commit()

if __name__ == "__main__":
    main()
