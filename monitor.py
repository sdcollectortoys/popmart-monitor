#!/usr/bin/env python3
import os, sys, time, uuid, signal, sqlite3, threading, random, requests
from http.server import BaseHTTPRequestHandler, HTTPServer

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ---- Health-check HTTP server ----
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        else:
            self.send_response(404); self.end_headers()

def start_health_server(port=10000):
    srv = HTTPServer(("", port), HealthHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

# ---- Pushover alert ----
PUSH_APP_TOKEN = os.environ["PUSHOVER_APP_TOKEN"]
PUSH_USER_KEY  = os.environ["PUSHOVER_USER_KEY"]
def send_pushover(msg: str):
    r = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": PUSH_APP_TOKEN, "user": PUSH_USER_KEY, "message": msg},
        timeout=10
    )
    r.raise_for_status()

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

# ---- undetected-chromedriver factory ----
def make_driver():
    opts = uc.ChromeOptions()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--window-size=1920,1080")
    # disable images for speed
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    # random UA to avoid fingerprinting
    ua = (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{random.randint(100,118)}.0.0.0 Safari/537.36"
    )
    opts.add_argument(f"--user-agent={ua}")

    # unique profile dir
    opts.add_argument(f"--user-data-dir=/tmp/stockmon-{uuid.uuid4()}")

    driver = uc.Chrome(options=opts)
    driver.set_page_load_timeout(20)
    return driver

# ---- Dismiss overlays ----
def accept_overlays(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[normalize-space()='I Agree' or normalize-space()='Accept' or contains(., 'Continue')]"
            ))
        )
        btn.click(); time.sleep(0.5)
    except TimeoutException:
        pass

# ---- Stock check ----
def check_stock(driver, url: str) -> str:
    driver.get(url)
    accept_overlays(driver)

    # wait up to 10s for the real “ADD TO BAG” div to appear in ANY tag
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//*[contains(translate(normalize-space(.),"
                " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                " 'abcdefghijklmnopqrstuvwxyz'), 'add to bag')]"
            ))
        )
    except TimeoutException:
        return "out"

    elems = driver.find_elements(By.XPATH,
        "//*[contains(translate(normalize-space(.),"
        " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        " 'abcdefghijklmnopqrstuvwxyz'), 'add to bag')]"
    )
    print(f"debug: found {len(elems)} ADD TO BAG element(s)")
    return "in" if elems else "out"

def sleep_until_top_of_minute():
    now = time.time(); delay = 60 - (now % 60)
    time.sleep(delay + random.uniform(0,1))

# ---- Main service ----
def main():
    urls = [u.strip() for u in os.environ.get("PRODUCT_URLS","").split(",") if u.strip()]
    if not urls:
        print("No PRODUCT_URLS configured; exiting."); sys.exit(1)

    conn = init_db(); cur = conn.cursor()
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
            for i in range(1,4):
                try:
                    state = check_stock(driver, url)
                    break
                except WebDriverException as e:
                    print(f"[Attempt {i}] error on {url}: {e}", file=sys.stderr)
                    time.sleep(i)
            if state is None:
                print(f"All attempts failed for {url}", file=sys.stderr)
                continue

            cur.execute("SELECT last_state FROM stock_state WHERE url = ?", (url,))
            row = cur.fetchone(); old = row[0] if row else "out"
            if old == "out" and state == "in":
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {url} → IN STOCK!")
                try: send_pushover(f"🔥 In stock: {url}")
                except Exception as e: print(f"Pushover error: {e}", file=sys.stderr)

            if not row:
                cur.execute(
                    "INSERT INTO stock_state(url,last_state,updated_at) "
                    "VALUES(?,?,CURRENT_TIMESTAMP)", (url, state)
                )
            else:
                cur.execute(
                    "UPDATE stock_state SET last_state=?, updated_at=CURRENT_TIMESTAMP WHERE url=?",
                    (state, url)
                )
            conn.commit()

if __name__ == "__main__":
    main()
