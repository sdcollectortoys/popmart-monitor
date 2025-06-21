#!/usr/bin/env python3
import os
import sys
import time
import logging
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ─── Configuration ─────────────────────────────────────────────────────────────
# Now reading PRODUCT_URLS, not URLS
raw = os.getenv("PRODUCT_URLS", "").strip()
URLS = [u.strip() for u in raw.split(",") if u.strip()]

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER  = os.getenv("PUSHOVER_USER")

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Push helper ────────────────────────────────────────────────────────────────
def send_push(title: str, message: str):
    if not (PUSHOVER_TOKEN and PUSHOVER_USER):
        logger.warning("Push credentials not set; skipping alert.")
        return
    resp = requests.post("https://api.pushover.net/1/messages.json", data={
        "token":  PUSHOVER_TOKEN,
        "user":   PUSHOVER_USER,
        "title":  title,
        "message": message
    })
    if resp.status_code == 200:
        logger.info("✔️ Pushover sent")
    else:
        logger.error(f"✖️ Pushover failed ({resp.status_code}): {resp.text}")

# ─── Browser setup ──────────────────────────────────────────────────────────────
def make_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver

# ─── Single-URL check ───────────────────────────────────────────────────────────
def check_stock(driver, url: str):
    logger.info(f"→ START {url}")
    try:
        driver.get(url)
    except Exception as e:
        logger.warning(f"⚠️ page-load failed: {e}")

    # 1) click the “Single box” option (if present)
    try:
        variant_xpath = (
            "//div[contains(@class,'index_sizeInfoTitle') "
            "and normalize-space(text())='Single box']"
        )
        el = driver.find_element(By.XPATH, variant_xpath)
        el.click()
        logger.info("Clicked Single box")
        time.sleep(1)
    except Exception as e:
        logger.debug(f"No variant click: {e}")

    # 2) look for the exact ADD TO BAG button
    try:
        stock_xpath = "//div[normalize-space(text())='ADD TO BAG']"
        found = driver.find_elements(By.XPATH, stock_xpath)
        if found:
            ts = time.strftime("%H:%M")
            logger.info(f"[{ts}] 🚨 IN STOCK → {url}")
            send_push("Popmart Restock!", f"{url} is IN STOCK at {ts}")
        else:
            logger.info("out of stock")
    except Exception as e:
        logger.error(f"Button scan failed: {e}")

    logger.info(f"← END   {url}")

# ─── Main loop ─────────────────────────────────────────────────────────────────
def main():
    if not URLS:
        logger.error("No URLs provided. Set the PRODUCT_URLS env var.")
        sys.exit(1)

    driver = make_driver()
    logger.info("Health check OK — headless Chrome ready")

    while True:
        logger.info("🔄 Cycle START")
        for u in URLS:
            check_stock(driver, u)
        logger.info("✅ Cycle END")
        # wait until top of next minute
        sleep_secs = 60 - (time.time() % 60)
        time.sleep(sleep_secs)

if __name__ == "__main__":
    main()
