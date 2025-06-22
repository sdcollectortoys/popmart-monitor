#!/usr/bin/env python3
import os
import sys
import time
import random
import signal
import sqlite3
import threading
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

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

def start_health_server(port: int = 10000):
    srv = HTTPServer(("", port), HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

# ---- Pushover alert ----
PUSH_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN") or os.environ["PUSHOVER_API_TOKEN"]
PUSH_USER_KEY  = os.environ["PUSHOVER_USER_KEY"]

def send_pushover(message: str):
    resp = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": PUSH_APP_TOKEN, "user": PUSH_USER_KEY, "message": message},
        timeout=10,
    )
    resp.raise_for_status()

# ---- SQLite persistence ----
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

# ---- Stock check via productDetails XHR ----
def check_stock(page, url: str) -> str:
    # Expect the productDetails XHR while navigating
    with page.expect_response(
        lambda r: "productDetails" in r.url and "spuId=" in r.url,
        timeout=10_000
    ) as resp_info:
        page.goto(url, wait_until="networkidle", timeout=30_000)
    resp = resp_info.value

    try:
        data = resp.json()
        skus = data.get("data", {}).get("skus", [])
    except Exception:
        return "out"

    for sku in skus:
        if sku.get("stock", {}).get("onlineStock", 0) > 0:
            return "in"
    return "out"

def sleep_until_top_of_minute():
    now = time.time()
    delay = 60 - (now % 60)
    time.sleep(delay + random.uniform(0, 1))

# ---- Main service ----
def main():
    urls = [
        u.strip()
        for u in os.environ.get("PRODUCT_URLS", "").split(",")
        if u.strip()
    ]
    if not urls:
        print("No PRODUCT_URLS configured; exiting.")
        sys.exit(1)

    conn = init_db()
    cur = conn.cursor()
    health_srv = start_health_server()

    def clean_exit(*_):
        print("Shutting down...")
        try: conn.close()
        except: pass
        try: health_srv.shutdown()
        except: pass
        sys.exit(0)

    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)

    print("Launching browser…")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=en-US",
                "--window-size=1920,1080",
            ]
        )
        context = browser.new_context(
            user_agent=(
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{random.randint(100,116)}.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        # Block image requests for speed
        context.route("**/*.{png,jpg,jpeg,svg,webp,gif}", lambda route: route.abort())
        page = context.new_page()

        print("Monitor started. Polling every minute.")
        while True:
            sleep_until_top_of_minute()
            for url in urls:
                state = None
                for attempt in range(1, 4):
                    try:
                        state = check_stock(page, url)
                        break
                    except PlaywrightTimeout as e:
                        print(f"[Attempt {attempt}] timeout on {url}: {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"[Attempt {attempt}] error on {url}: {e}", file=sys.stderr)
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
                        "INSERT INTO stock_state(url, last_state, updated_at) "
                        "VALUES (?, ?, CURRENT_TIMESTAMP)",
                        (url, state)
                    )
                else:
                    cur.execute(
                        "UPDATE stock_state "
                        "SET last_state = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE url = ?",
                        (state, url)
                    )
                conn.commit()

        browser.close()

if __name__ == "__main__":
    main()
