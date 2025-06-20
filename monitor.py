#!/usr/bin/env python3
import os
import time
import logging
import threading
import json
from urllib.parse import urlparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8000"))
PUSH_KEY        = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN      = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL","60"))
REQUEST_TIMEOUT = 10  # seconds

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; stock-monitor/1.0)"
}

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
            data={"token": PUSH_TOKEN, "user": PUSH_KEY, "message": msg},
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

# ─── SINGLE CHECK ──────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ START {url}")
    # 1) fetch initial HTML to grab buildId
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logging.error("HTTP error fetching %s: %s", url, e)
        return

    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if not script or not script.string:
        logging.error("   no __NEXT_DATA__ JSON on page")
        return

    try:
        data = json.loads(script.string)
        build_id = data["buildId"]
    except Exception as e:
        logging.error("   failed to parse buildId: %s", e)
        return

    # 2) build JSON URL
    parsed = urlparse(url)
    suffix = parsed.path.lstrip("/")  # e.g. "us/products/2767/Care%20Bears…"
    json_url = f"{parsed.scheme}://{parsed.netloc}/_next/data/{build_id}/{suffix}.json"

    # 3) fetch server‐side JSON
    try:
        j = requests.get(json_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        j.raise_for_status()
        payload = j.json()
    except Exception as e:
        logging.error("   error fetching JSON %s: %s", json_url, e)
        return

    # 4) dig out the product info
    page_props = payload.get("pageProps", {})
    prod = page_props.get("product")
    if not prod:
        logging.error("   no 'product' in JSON pageProps")
        return

    # 5) read soldOut on default variant
    sku_infos = prod.get("skuInfos", [])
    if not sku_infos:
        logging.error("   no skuInfos in product")
        return

    sold_out = sku_infos[0].get("soldOut", True)
    in_stock = not sold_out
    logging.info(f"   debug JSON soldOut={sold_out}, inStock={in_stock}")

    # 6) alert
    if in_stock:
        msg = f"[{datetime.now():%H:%M}] IN STOCK → {url}"
        logging.info(msg)
        send_pushover(msg)
    else:
        logging.info("   out of stock")

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
