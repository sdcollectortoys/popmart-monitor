#!/usr/bin/env python3
import os
import sys
import time
import json
import re
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────

# Your list of SPU IDs to monitor
SPUS = ["878", "890", "2155", "2879", "2492"]

# How often (seconds) between polls
INTERVAL = 60

# Pushover credentials (set these in your Render env)
PUSHOVER_APP_TOKEN = os.environ["PUSHOVER_API_TOKEN"]
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]

# Port to bind HTTP health‐check server on (Render will provide $PORT)
PORT = int(os.environ.get("PORT", 8000))


# ─── LOGGING ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("monitor")


# ─── HEALTH CHECK SERVER ───────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def _respond_200(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            return self._respond_200()
        # you can add other paths here if needed
        self.send_error(404)

    def do_HEAD(self):
        # support HEAD for /health so probes don’t get 501
        if self.path == "/health":
            return self._respond_200()
        self.send_error(404)

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health check server listening on 0.0.0.0:{PORT}")
    server.serve_forever()


# ─── STOCK FETCHER ─────────────────────────────────────────────────────────

def fetch_stock(spu_id: str) -> bool:
    """
    Fetch the product page HTML as a real Chrome UA,
    extract the Next.js JSON blob, locate `props.pageProps.productDetails.skus`,
    and return True if any sku.stock.onlineStock > 0.
    """
    url = f"https://www.popmart.com/us/products/{spu_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"[SPU {spu_id}] network error: {e}")
        return False

    # extract the inline JSON blob
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        flags=re.DOTALL
    )
    if not m:
        logger.error(f"[SPU {spu_id}] __NEXT_DATA__ blob not found")
        return False

    try:
        blob = json.loads(m.group(1))
        props = blob.get("props", {}).get("pageProps", {})

        # debug: log what keys we actually got in pageProps
        logger.debug(f"[SPU {spu_id}] pageProps keys = {list(props.keys())}")

        # drill into the right spot
        if "productDetails" in props:
            pd = props["productDetails"]
        elif "product" in props and isinstance(props["product"], dict):
            pd = props["product"].get("productDetails", {})
        else:
            logger.error(f"[SPU {spu_id}] no productDetails key in pageProps")
            return False

        # look for any sku with stock > 0
        for sku in pd.get("skus", []):
            if sku.get("stock", {}).get("onlineStock", 0) > 0:
                return True

    except Exception as e:
        logger.error(f"[SPU {spu_id}] error parsing JSON: {e}")
        return False

    return False


# ─── PUSHOVER ───────────────────────────────────────────────────────────────

def send_push(spu_id: str):
    link = f"https://www.popmart.com/us/products/{spu_id}"
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": f"POP MART In Stock!",
        "message": f"SPU {spu_id} is now in stock: {link}",
        # you can add "sound", "priority", etc.
    }
    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data=data, timeout=10)
        r.raise_for_status()
        logger.info(f"[SPU {spu_id}] Pushover notification sent")
    except Exception as e:
        logger.error(f"[SPU {spu_id}] error sending Pushover: {e}")


# ─── MAIN MONITOR LOOP ──────────────────────────────────────────────────────

def monitor_loop():
    last_in_stock = {spu: False for spu in SPUS}
    logger.info(f"Monitor started. Polling every {INTERVAL} seconds for SPUs: {SPUS}")

    while True:
        logger.info("🔄 Cycle START")
        for spu in SPUS:
            try:
                in_stock = fetch_stock(spu)
                if in_stock:
                    logger.info(f"[SPU {spu}] → IN STOCK")
                else:
                    logger.info(f"[SPU {spu}] out of stock")

                # if newly in stock, fire notification
                if in_stock and not last_in_stock[spu]:
                    send_push(spu)

                last_in_stock[spu] = in_stock

            except Exception as e:
                logger.error(f"[SPU {spu}] unexpected error: {e}")

        logger.info("✅ Cycle END")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    # start HTTP health server in background
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    try:
        monitor_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down monitor")
        sys.exit(0)
