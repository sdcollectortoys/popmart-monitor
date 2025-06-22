#!/usr/bin/env python3
import os
import re
import sys
import time
import logging
import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Comma-separated product URLs, e.g. "https://…/products/2492,https://…/products/2155"
URLS         = os.environ.get("MONITOR_URLS", "").split(",")
INTERVAL     = int(os.environ.get("MONITOR_INTERVAL", "60"))
PUSH_APP_TOKEN = os.environ["PUSHOVER_API_TOKEN"]
PUSH_USER_KEY  = os.environ["PUSHOVER_USER_KEY"]
PUSH_URL       = "https://api.pushover.net/1/messages.json"

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)5s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("popmart-monitor")

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_spu_id_from_url(url: str) -> str:
    m = re.search(r"/products/(\d+)", url)
    return m.group(1) if m else None

def fetch_stock(spu_id: str) -> bool:
    """
    Returns True if any SKU for this SPU has onlineStock > 0.
    """
    resp = requests.get(
        "https://prod-na-api.popmart.com/shop/v1/shop/productDetails",
        params={"spuId": spu_id},
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (popmart-stock-checker)"
        },
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    skus = data.get("skus", [])
    return any(sku["stock"]["onlineStock"] > 0 for sku in skus)

def notify(title: str, message: str) -> None:
    payload = {
        "token": PUSH_APP_TOKEN,
        "user":  PUSH_USER_KEY,
        "title": title,
        "message": message,
    }
    r = requests.post(PUSH_URL, data=payload, timeout=5)
    r.raise_for_status()

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    # initialize all as “out of stock”
    last_state = {url: False for url in URLS}

    logger.info("Starting monitor — polling every %s seconds for %d URLs",
                INTERVAL, len(URLS))

    while True:
        for url in URLS:
            url = url.strip()
            spu = get_spu_id_from_url(url)
            if not spu:
                logger.error("Could not parse SPU from URL: %s", url)
                continue

            try:
                in_stock = fetch_stock(spu)
            except Exception:
                logger.exception("Error fetching stock for SPU %s", spu)
                in_stock = False

            if in_stock and not last_state[url]:
                logger.info("🔔 %s JUST CAME IN STOCK!", url)
                notify("POP MART In-Stock!", url)
            else:
                logger.debug("%s is %s", url, "IN-STOCK" if in_stock else "OOS")

            last_state[url] = in_stock

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
