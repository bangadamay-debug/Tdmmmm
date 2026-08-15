import os
import time
import random
import string
import logging

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
    filters,
    ContextTypes,
    ConversationHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = "PASTE_YOUR_BOTFATHER_TOKEN_HERE"

PROXY_HOST = "p1.arealproxy.com"
PROXY_PORT = "9000"
PROXY_USER = "490ddebb69a88445c2-type-residential"
PROXY_PASS = "775cbe4d-17ba-4ec7-91ff-7e9698861ac6"

VOUCHER, MOBILE, OTP = range(3)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["🚀 Start Claim", "➕ New Entry"], ["❌ Cancel"]],
    resize_keyboard=True,
)
CANCEL_KEYBOARD = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)


def get_random_name():
    first_names = [
        "Amit", "Rahul", "Suresh", "Priya", "Anjali",
        "Vikram", "Neha", "Rohan", "Sneha", "Arjun",
    ]
    last_names = [
        "Sharma", "Verma", "Gupta", "Singh",
        "Kumar", "Jain", "Mehta", "Patel",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def get_random_email():
    chars = string.ascii_lowercase + string.digits
    username = "".join(random.choice(chars) for _ in range(8))
    return f"{username}@gmail.com"


class OnamAutomator:
    def __init__(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # Use the proxy only if the required credentials are available.
        options.add_argument(f"--proxy-server={PROXY_HOST}:{PROXY_PORT}")

        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        options.add_experimental_option("useAutomationExtension", False)

        # Do not hard-code /usr/bin/google-chrome. Selenium Manager can
        # locate the browser/driver on GitHub Actions.
        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 20)
        except Exception as e:
            logger.exception("Chrome initialization failed")
            raise e

    def get_site_response(self):
        try:
            selectors = [
                ".error",
                ".alert-danger",
                "#error-msg",
                "span[style*='color: red']",
                "div[style*='color: red']",
            ]
            for selector in selectors:
                for el in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    if el.is_displayed() and el.text.strip():
                        return el.text.strip()

            body = self.driver.find_element(By.TAG_NAME, "body").text.lower()

            if "already registered" in body:
                return "Voucher or Mobile is already registered."
            if "limit exceeded" in body:
                return "Promo limit exceeded for this number."
            if "invalid voucher" in body:
                return "Invalid Voucher Code."
            if "thank you" in body or "success" in body:
                return "Success!"

            return None
        except Exception:
            return None

    async def start_claim(self, voucher, mobile, status_update_fn):
        try:
            await status_update_fn("⚡ Opening website...")
            self.driver.get("https://www.happiestonam.com/")

            await status_update_fn("⚡ Waiting for form...")
            self.wait.until(
                EC.presence_of_element_located((By.ID, "vouchercode"))
            )

            await status_update_fn("⚡ Filling details...")

            self.driver.find_element(By.ID, "vouchercode").send_keys(voucher)
            self.driver.find_element(By.ID, "name").send_keys(get_random_name())
            self.driver.find_element(By.ID, "email").send_keys(get_random_email())
            self.driver.find_element(By.ID, "mobile").send_keys(mobile[-10:])

            try:
                checkbox = self.driver.find_element(By.ID, "terms_cond")
                if not checkbox.is_selected():
                    checkbox.click()
            except Exception:
                pass

            self.driver.find_element(By.ID, "enbBtn").click()

            # OTP is checked only AFTER the initial form is submitted.
            await status_update_fn("⚡ Waiting for OTP field...")
            self.wait.until(
                EC.presence_of_element_located((By.ID, "otp"))
            )
            return True, "OTP field appeared."

        except Exception as e:
            err = self.get_site_response()
            return False, err or f"Error: {str(e)[:150]}"

    async def submit_otp_and_choose_upi(self, otp, status_update_fn):
        try:
            await status_update_fn("⚡ Submitting OTP...")

            otp_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "otp"))
            )
            otp_input.clear()
            otp_input.send_keys(otp)

            # The submit button may be reused after OTP.
            buttons = self.driver.find_elements(
                By.XPATH,
                "//button | //input[@type='submit']"
            )
            clicked = False

            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                return False, "Could not find the OTP submit button."

            await status_update_fn("⚡ Verifying OTP...")
            time.sleep(2)

            # Wait for the next state to render.
            self.wait.until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            await status_update_fn("⚡ Looking for UPI option...")

            if self._choose_upi_option():
                await status_update_fn("✅ UPI option selected.")
                return True, "UPI option selected successfully."

            err = self.get_site_response()
            return False, err or "UPI option was not found."

        except Exception as e:
            return False, f"Error: {str(e)[:150]}"

    def _choose_upi_option(self):
        """
        Select a visible UPI payment option. This intentionally does not
        enter a UPI ID or submit a payment.
        """
        # First try radio/checkbox inputs whose attributes identify UPI.
        inputs = self.driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='radio'], input[type='checkbox']"
        )

        for el in inputs:
            try:
                attrs = " ".join(
                    [
                        el.get_attribute("id") or "",
                        el.get_attribute("name") or "",
                        el.get_attribute("value") or "",
                        el.get_attribute("aria-label") or "",
                    ]
                ).lower()

                if "upi" in attrs and el.is_displayed():
                    self.driver.execute_script(
                        "arguments[0].click();", el
                    )
                    return True
            except Exception:
                continue

        # Then try visible labels/buttons/links containing "UPI".
        candidates = self.driver.find_elements(
            By.XPATH,
            "//label | //button | //a | "
            "//*[@role='radio'] | //*[@role='button'] | "
            "//*[contains(@class,'payment')]"
        )

        for el in candidates:
            try:
                text = (
                    (el.text or "") + " " +
                    (el.get_attribute("aria-label") or "") + " " +
                    (el.get_attribute("data-value") or "") + " " +
                    (el.get_attribute("id") or "")
                ).strip().lower()

                if "upi" in text and el.is_displayed() and el.is_enabled():
                    self.driver.execute_script(
                        "arguments[0].click();", el
                    )
                    return True
            except Exception:
                continue

        return False

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ Onam Bot Active\n\nUse the buttons below to start.",
        reply_markup=MAIN_KEYBOARD,
    )


async def claim_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎟 Send Voucher Code:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return VOUCHER


async def get_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Cancel":
        return await cancel(update, context)

    context.user_data["voucher"] = text

    await update.message.reply_text(
        "📱 Send Mobile Number:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return MOBILE


async def get_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Cancel":
        return await cancel(update, context)

    if not text.isdigit() or len(text) < 10:
        await update.message.reply_text(
            "❌ Invalid number. Send 10 digits:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return MOBILE

    context.user_data["mobile"] = text
    voucher = context.user_data["voucher"]

    status_msg = await update.message.reply_text(
        f"⚡ Starting `{voucher}`...",
        parse_mode="Markdown",
    )

    async def update_status(message):
        try:
            await status_msg.edit_text(message, parse_mode="Markdown")
        except Exception:
            pass

    try:
        automator = OnamAutomator()
        context.user_data["automator"] = automator

        success, msg = await automator.start_claim(
            voucher, text, update_status
        )

        if success:
            await update_status("✅ Details submitted. Send OTP:")
            return OTP

        await update_status(f"❌ Error:\n`{msg}`")
        automator.close()
        return ConversationHandler.END

    except Exception as e:
        await update_status(f"❌ System Error:\n`{str(e)[:150]}`")
        return ConversationHandler.END


async def get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Cancel":
        return await cancel(update, context)

    automator = context.user_data.get("automator")

    if not automator:
        await update.message.reply_text(
            "❌ Session expired. Start again.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    async def update_status(message):
        try:
            await update.message.reply_text(message)
        except Exception:
            pass

    success, msg = await automator.submit_otp_and_choose_upi(
        text, update_status
    )

    if success:
        await update.message.reply_text(
            f"🎉 {msg}",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text(
            f"❌ Error:\n{msg}",
            reply_markup=MAIN_KEYBOARD,
        )

    automator.close()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    automator = context.user_data.get("automator")

    if automator:
        automator.close()

    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOTFATHER_TOKEN_HERE":
        logger.error("BOT_TOKEN is not configured.")
        print(
            "ERROR: Set the BOT_TOKEN GitHub secret or put your "
            "BotFather token in the file."
        )
        return

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🚀 Start Claim$"), claim_start
            ),
            MessageHandler(
                filters.Regex("^➕ New Entry$"), claim_start
            ),
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
            OTP: [
                MessageHandler(
                    filters.TEXT & ~filters.Regex("^❌ Cancel$"),
                    get_otp,
                )
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    print("🚀 Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
