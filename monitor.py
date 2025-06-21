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

# Comma-separated list of full product URLs in ENV var URLS
URLS = os.getenv("URLS", "").split(",")

# Pushover (or whatever) credentials
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER  = os.getenv("PUSHOVER_USER")

# ─── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s %(levelname)7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Helper to fire off a push alert ────────────────────────────────────────────

def send_push(title: str, message: str):
    if not (PUSHOVER_TOKEN and PUSHOVER_USER):
        logger.warning("Push credentials not set; skipping alert.")
        return
    r = requests.post("https://api.pushover.net/1/messages.json", data={
        "token":   PUSHOVER_TOKEN,
        "user":    PUSHOVER_USER,
        "title":   title,
        "message": message
    })
    if r.status_code == 200:
        logger.info("✔️ Pushover sent")
    else:
        logger.error(f"✖️ Pushover failed: {r.status_code} {r.text}")

# ─── Browser setup ──────────────────────────────────────────────────────────────

def make_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    # limit how long get() can hang
    driver.set_page_load_timeout(30)
    return driver

# ─── Core check for one URL ─────────────────────────────────────────────────────

def check_stock(driver, url: str):
    url = url.strip()
    if not url:
        return

    logger.info(f"→ START {url}")
    try:
        driver.get(url)
    except Exception as e:
        logger.warning(f"⚠️ page-load failed: {e}")

    # 1) Click the “Single box” toggle to ensure the single‐unit inventory is active
    try:
        single_xpath = (
            "//div[contains(@class,'index_sizeInfoTitle') "
            "and normalize-space(text())='Single box']"
        )
        btn = driver.find_element(By.XPATH, single_xpath)
        btn.click()
        logger.info("Clicked Single box")
        time.sleep(1)
    except Exception as e:
        logger.warning(f"Variant click failed: {e}")

    # 2) Look *only* for the EXACT “ADD TO BAG” button
    try:
        stock_xpath = "//div[normalize-space(text())='ADD TO BAG']"
        elems = driver.find_elements(By.XPATH, stock_xpath)
        if elems:
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
    if not URLS or URLS == [""]:
        logger.error("No URLs provided. Set the URLS env var.")
        sys.exit(1)

    driver = make_driver()

    # Warm up
    logger.info("Health check listening (headless Chrome up)")

    # Run forever, aligned to the top of each minute
    while True:
        logger.info("🔄 Cycle START")
        for u in URLS:
            check_stock(driver, u)
        logger.info("✅ Cycle END")
        # sleep until next minute
        time_to_next = 60 - (time.time() % 60)
        time.sleep(time_to_next)

if __name__ == "__main__":
    main()
