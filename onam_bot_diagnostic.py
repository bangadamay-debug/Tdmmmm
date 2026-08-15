import os
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

URL = "https://www.happiestonam.com/"
OUT = Path("diagnostics")
OUT.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1365,900")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(URL)

        # Give the page a short, bounded amount of time to load.
        driver.implicitly_wait(5)

        checks = {
            "vouchercode": "vouchercode",
            "name": "name",
            "email": "email",
            "mobile": "mobile",
            "terms_cond": "terms_cond",
            "enbBtn": "enbBtn",
            "otp": "otp",
        }

        found = []
        missing = []

        for label, element_id in checks.items():
            try:
                driver.find_element(By.ID, element_id)
                found.append(label)
            except Exception:
                missing.append(label)

        html_path = OUT / "selenium_diagnostic.html"
        png_path = OUT / "selenium_diagnostic.png"

        html_path.write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(png_path))

        logging.info("Page URL: %s", driver.current_url)
        logging.info("Page title: %s", driver.title)
        logging.info("FOUND: %s", ", ".join(found) if found else "none")
        logging.info("MISSING: %s", ", ".join(missing) if missing else "none")
        logging.info("Saved %s", html_path)
        logging.info("Saved %s", png_path)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
