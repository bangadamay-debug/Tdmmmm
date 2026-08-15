import os
import logging
import asyncio

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Optional proxy settings. Put these in GitHub Secrets/environment variables.
PROXY_HOST = os.environ.get("PROXY_HOST", "").strip()
PROXY_PORT = os.environ.get("PROXY_PORT", "").strip()

VOUCHER, MOBILE = range(2)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["🚀 Start Claim"], ["❌ Cancel"]],
    resize_keyboard=True,
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [["❌ Cancel"]],
    resize_keyboard=True,
)


# ---------------- SELENIUM DIAGNOSTICS ----------------
class PageDiagnostic:
    def __init__(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")

        if PROXY_HOST and PROXY_PORT:
            options.add_argument(f"--proxy-server={PROXY_HOST}:{PROXY_PORT}")

        # Let Selenium Manager locate the installed browser/driver.
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

    def diagnose(self, url):
        self.driver.get(url)

        # Give JavaScript a little time to render.
        import time
        time.sleep(3)

        current_url = self.driver.current_url
        title = self.driver.title

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception as exc:
            body_text = f"<unable to read body: {exc}>"

        expected_ids = [
            "vouchercode",
            "name",
            "email",
            "mobile",
            "terms_cond",
            "enbBtn",
            "otp",
        ]

        found = []
        missing = []

        for element_id in expected_ids:
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.ID, element_id))
                )
                found.append(element_id)
                logger.info("FOUND element id=%s", element_id)
            except Exception:
                missing.append(element_id)
                logger.error("MISSING element id=%s", element_id)

        screenshot = "selenium_diagnostic.png"
        html = "selenium_diagnostic.html"

        try:
            self.driver.save_screenshot(screenshot)
            logger.info("Saved %s", screenshot)
        except Exception:
            logger.exception("Could not save screenshot")

        try:
            with open(html, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info("Saved %s", html)
        except Exception:
            logger.exception("Could not save HTML")

        return {
            "url": current_url,
            "title": title,
            "body": body_text[:3000],
            "found": found,
            "missing": missing,
            "screenshot": screenshot,
            "html": html,
        }

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass


# ---------------- BOT HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ Selenium diagnostic bot is running.\n\n"
        "This version checks the webpage and reports missing elements. "
        "It does not submit OTP or UPI transactions.",
        reply_markup=MAIN_KEYBOARD,
    )


async def claim_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send the voucher code:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return VOUCHER


async def get_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "❌ Cancel":
        return await cancel(update, context)

    if not text:
        await update.message.reply_text("Please send a voucher code.")
        return VOUCHER

    context.user_data["voucher"] = text

    await update.message.reply_text(
        "Send the mobile number:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return MOBILE


async def get_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "❌ Cancel":
        return await cancel(update, context)

    if not text.isdigit() or len(text) < 10:
        await update.message.reply_text(
            "Invalid number. Send a valid mobile number.",
            reply_markup=CANCEL_KEYBOARD,
        )
        return MOBILE

    status = await update.message.reply_text(
        "⚡ Opening webpage and checking Selenium elements..."
    )

    diagnostic = None

    try:
        diagnostic = PageDiagnostic()

        result = await asyncio.to_thread(
            diagnostic.diagnose,
            "https://www.happiestonam.com/",
        )

        found = ", ".join(result["found"]) if result["found"] else "none"
        missing = ", ".join(result["missing"]) if result["missing"] else "none"

        message = (
            "🔎 Diagnostic result\n\n"
            f"URL:\n{result['url']}\n\n"
            f"Title:\n{result['title']}\n\n"
            f"FOUND:\n{found}\n\n"
            f"MISSING:\n{missing}\n\n"
            "A screenshot and HTML file were created on the runner."
        )

        # Telegram messages have a size limit.
        await status.edit_text(message[:4000])

        logger.info("Page URL: %s", result["url"])
        logger.info("Page title: %s", result["title"])
        logger.info("Found elements: %s", found)
        logger.info("Missing elements: %s", missing)
        logger.info("Body preview:\n%s", result["body"])

    except Exception as exc:
        logger.exception("Selenium diagnostic failed")

        try:
            await status.edit_text(
                "❌ Selenium diagnostic failed:\n"
                f"{type(exc).__name__}: {exc}"
            )
        except Exception:
            pass

    finally:
        if diagnostic:
            diagnostic.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not configured.")
        print("ERROR: Set BOT_TOKEN as a GitHub Actions secret/environment variable.")
        return

    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as exc:
        logger.exception("Telegram initialization failed")
        print(f"ERROR: Telegram initialization failed: {exc}")
        return

    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🚀 Start Claim$"),
                claim_start,
            )
        ],
        states={
            VOUCHER: [
                MessageHandler(
                    filters.TEXT & ~filters.Regex("^❌ Cancel$"),
                    get_voucher,
                )
            ],
            MOBILE: [
                MessageHandler(
                    filters.TEXT & ~filters.Regex("^❌ Cancel$"),
                    get_mobile,
                )
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex("^❌ Cancel$"),
                cancel,
            ),
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conversation)

    print("🚀 Selenium diagnostic bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
