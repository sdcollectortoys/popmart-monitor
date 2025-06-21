#!/usr/bin/env python3
import os
import time
import logging
import threading
import json
from datetime import datetime
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8000"))
PUSH_KEY        = os.getenv("PUSHOVER_USER_KEY")
PUSH_TOKEN      = os.getenv("PUSHOVER_API_TOKEN")
PRODUCT_URLS    = [u.strip() for u in os.getenv("PRODUCT_URLS","").split(",") if u.strip()]
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL","60"))
REQUEST_TIMEOUT = 10  # seconds per HTTP request

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-monitor/1.0)"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
    httpd = HTTPServer(("", PORT), HealthHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logging.info(f"Health check listening on port {PORT}")

# ─── PUSHOVER ──────────────────────────────────────────────────────────────────
def send_pushover(msg: str):
    if not (PUSH_KEY and PUSH_TOKEN):
        logging.warning("Missing Pushover credentials; skipping alert")
        return
    try:
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": PUSH_TOKEN, "user": PUSH_KEY, "message": msg},
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        logging.info("✔️ Pushover sent")
    except Exception as e:
        logging.error("Pushover error: %s", e)

# ─── SINGLE CHECK ──────────────────────────────────────────────────────────────
def check_stock(url: str):
    logging.info(f"→ START {url}")

    # 1) Fetch initial HTML for __NEXT_DATA__
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logging.error("HTTP error fetching %s: %s", url, e)
        return

    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if not script or not script.string:
        logging.error("   no __NEXT_DATA__ on page")
        return

    # 2) Parse __NEXT_DATA__ to get buildId + route template + query
    try:
        d        = json.loads(script.string)
        build_id = d["buildId"]
        page_tpl = d.get("page", "")      # e.g. "/us/products/[id]/[slug]"
        query    = d.get("query", {})     # contains "id" and "slug"
        if not page_tpl or "id" not in query or "slug" not in query:
            logging.error("   cannot reconstruct route; missing page or query")
            return

        # fill in the template
        route = page_tpl.replace("[id]", str(query["id"])).replace("[slug]", query["slug"])
    except Exception as e:
        logging.error("   parsing __NEXT_DATA__ failed: %s", e)
        return

    parsed = urlparse(url)
    host   = f"{parsed.scheme}://{parsed.netloc}"

    # 3) Try dynamic Next.js JSON, then static fallback
    dyn_url = f"{host}/_next/data/{build_id}{route}.json"
    static_url = f"{host}{route}.json"
    for candidate in (dyn_url, static_url):
        logging.info(f"   debug: trying JSON at {candidate}")
        try:
            jr = requests.get(candidate, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if jr.status_code != 200:
                continue
            payload = jr.json()
            break
        except Exception:
            continue
    else:
        logging.error("   all JSON endpoints failed")
        return

    # 4) Extract soldOut flag
    try:
        prod      = payload["pageProps"]["product"]
        sku_infos = prod.get("skuInfos", [])
        sold_out  = sku_infos[0].get("soldOut", True) if sku_infos else True
        in_stock  = not sold_out
        logging.info(f"   debug JSON soldOut={sold_out}, inStock={in_stock}")
    except Exception as e:
        logging.error("   JSON parse error: %s", e)
        return

    # 5) Alert if in stock
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
    # align to the next interval
    time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))
    while True:
        logging.info("🔄 Cycle START")
        for u in PRODUCT_URLS:
            check_stock(u)
        logging.info("✅ Cycle END")
        time.sleep(CHECK_INTERVAL - (time.time() % CHECK_INTERVAL))

if __name__=="__main__":
    main()
