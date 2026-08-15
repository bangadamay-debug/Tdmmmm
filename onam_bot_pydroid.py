import os
import time
import random
import string
import logging
import asyncio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
# Pydroid/Android: put your BotFather token here.
# Keep this file private and never publish the token.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = "PASTE_YOUR_BOTFATHER_TOKEN_HERE"

# Proxy Details (ArealProxy)
PROXY_HOST = "p1.arealproxy.com"
PROXY_PORT = "9000"
PROXY_USER = "490ddebb69a88445c2-type-residential"
PROXY_PASS = "775cbe4d-17ba-4ec7-91ff-7e9698861ac6"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Conversation States
VOUCHER, MOBILE, OTP, UPI = range(4)

# Keyboards
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ["🚀 Start Claim", "➕ New Entry"],
    ["❌ Cancel"]
], resize_keyboard=True)

CANCEL_KEYBOARD = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)

# --- UTILS ---
def get_random_name():
    first_names = ["Amit", "Rahul", "Suresh", "Priya", "Anjali", "Vikram", "Neha", "Rohan", "Sneha", "Arjun"]
    last_names = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Jain", "Mehta", "Patel"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def get_random_email():
    chars = string.ascii_lowercase + string.digits
    username = ''.join(random.choice(chars) for _ in range(8))
    return f"{username}@gmail.com"

# --- SELENIUM CORE ---
class OnamAutomator:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Proxy Integration for Ultra-Fast & Stable Connection
        chrome_options.add_argument(f"--proxy-server={PROXY_HOST}:{PROXY_PORT}")
        
        # Speed Optimization: Disable images and heavy features
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        chrome_options.binary_location = "/usr/bin/google-chrome"
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            # Bypass webdriver detection
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            self.wait = WebDriverWait(self.driver, 15)
        except Exception as e:
            logger.error(f"Chrome init failed: {e}")
            raise e

    def get_site_response(self):
        try:
            error_selectors = [".error", ".alert-danger", "#error-msg", "span[style*='color: red']", "div[style*='color: red']"]
            for selector in error_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed() and el.text.strip(): return el.text.strip()
            
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if "already registered" in body_text: return "Voucher or Mobile is already registered."
            if "limit exceeded" in body_text: return "Promo limit exceeded for this number."
            if "invalid voucher" in body_text: return "Invalid Voucher Code."
            if "thank you" in body_text or "success" in body_text: return "Success!"
            return None
        except: return None

    async def start_claim(self, voucher, mobile, status_update_fn):
        try:
            await status_update_fn("⚡ Connecting via Proxy...")
            self.driver.get("https://www.happiestonam.com/")
            
            # Ultra-Fast Dynamic Wait for Form
            await status_update_fn("⚡ Waiting for Form...")
            try:
                self.wait.until(EC.presence_of_element_located((By.ID, "vouchercode")))
            except:
                # If not found immediately, maybe Cloudflare is active
                await status_update_fn("⏳ Handling Cloudflare...")
                time.sleep(5)
            
            await status_update_fn("⚡ Filling Details...")
            self.driver.find_element(By.ID, "vouchercode").send_keys(voucher)
            self.driver.find_element(By.ID, "name").send_keys(get_random_name())
            self.driver.find_element(By.ID, "email").send_keys(get_random_email())
            self.driver.find_element(By.ID, "mobile").send_keys(mobile[-10:])
            
            try:
                cb = self.driver.find_element(By.ID, "terms_cond")
                if not cb.is_selected(): cb.click()
            except: pass
            
            self.driver.find_element(By.ID, "enbBtn").click()
            
            # Dynamic Wait for OTP field
            await status_update_fn("⚡ Waiting for OTP Field...")
            try:
                self.wait.until(EC.presence_of_element_located((By.ID, "otp")))
                return True, "OTP field appeared."
            except:
                err = self.get_site_response()
                return False, err if err else "OTP field not found. Site may be slow."
        except Exception as e: return False, f"Error: {str(e)[:50]}"

    async def submit_otp(self, otp, status_update_fn):
        try:
            await status_update_fn("⚡ Submitting OTP...")
            self.driver.find_element(By.ID, "otp").send_keys(otp)
            self.driver.find_element(By.ID, "enbBtn").click()
            
            await status_update_fn("⚡ Verifying...")
            try:
                # Wait for UPI field
                self.wait.until(lambda d: any("upi" in (i.get_attribute("placeholder") or "").lower() or "upi" in (i.get_attribute("name") or "").lower() for i in d.find_elements(By.TAG_NAME, "input")))
                return True, "UPI field found."
            except:
                err = self.get_site_response()
                return False, err if err else "OTP verification failed."
        except Exception as e: return False, str(e)

    async def submit_upi(self, upi_id, status_update_fn):
        try:
            await status_update_fn("⚡ Submitting UPI ID...")
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            upi_input = None
            for inp in inputs:
                attr = (inp.get_attribute("placeholder") or "") + (inp.get_attribute("name") or "") + (inp.get_attribute("id") or "")
                if "upi" in attr.lower(): upi_input = inp; break
            
            if upi_input:
                upi_input.send_keys(upi_id)
                self.driver.find_element(By.XPATH, "//button | //input[@type='submit']").click()
                
                await status_update_fn("⚡ Finishing...")
                time.sleep(3) # Short wait for final result
                
                final_res = self.get_site_response()
                if final_res: return True, final_res
                
                body = self.driver.find_element(By.TAG_NAME, "body").text
                if "success" in body.lower() or "thank you" in body.lower(): return True, "Claim Successfully Completed!"
                return True, "Process finished."
            return False, "UPI field not found."
        except Exception as e: return False, str(e)

    def close(self):
        try: self.driver.quit()
        except: pass

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ **Ultra-Fast Onam Bot Active**\n\nUse the buttons below to start.", reply_markup=MAIN_KEYBOARD, parse_mode="Markdown")

async def claim_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎟 Send **Voucher Code**:", parse_mode="Markdown", reply_markup=CANCEL_KEYBOARD)
    return VOUCHER

async def get_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel": return await cancel(update, context)
    context.user_data['voucher'] = text
    await update.message.reply_text("📱 Send **Mobile Number**:", reply_markup=CANCEL_KEYBOARD)
    return MOBILE

async def get_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel": return await cancel(update, context)
    if not text.isdigit() or len(text) < 10:
        await update.message.reply_text("❌ Invalid number. Send 10 digits:", reply_markup=CANCEL_KEYBOARD)
        return MOBILE
    
    context.user_data['mobile'] = text
    voucher = context.user_data['voucher']
    status_msg = await update.message.reply_text(f"⚡ Starting `{voucher}`...", parse_mode="Markdown")
    
    async def update_status(new_text):
        try: await status_msg.edit_text(new_text, parse_mode="Markdown")
        except: pass

    try:
        automator = OnamAutomator()
        context.user_data['automator'] = automator
        success, msg = await automator.start_claim(voucher, text, update_status)
        
        if success:
            await update_status("✅ Details filled. **Send OTP**:")
            return OTP
        else:
            await update_status(f"❌ **Error:**\n`{msg}`")
            automator.close(); return ConversationHandler.END
    except Exception as e:
        await update_status(f"❌ **System Error:** {str(e)[:100]}")
        return ConversationHandler.END

async def get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel": return await cancel(update, context)
    automator = context.user_data.get('automator')
    
    async def update_status(new_text):
        try: await update.message.reply_text(new_text, parse_mode="Markdown")
        except: pass

    success, msg = await automator.submit_otp(text, update_status)
    if success:
        await update.message.reply_text("✅ OTP Verified! **Send UPI ID**:", parse_mode="Markdown", reply_markup=CANCEL_KEYBOARD)
        return UPI
    else:
        await update.message.reply_text(f"❌ **Error:**\n`{msg}`", reply_markup=MAIN_KEYBOARD)
        if automator: automator.close()
        return ConversationHandler.END

async def get_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel": return await cancel(update, context)
    automator = context.user_data.get('automator')
    
    async def update_status(new_text):
        try: await update.message.reply_text(new_text, parse_mode="Markdown")
        except: pass

    success, msg = await automator.submit_upi(text, update_status)
    if success: await update.message.reply_text(f"🎉 **Final Result:**\n{msg}", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    else: await update.message.reply_text(f"❌ **Error:**\n{msg}", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    if automator: automator.close()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    automator = context.user_data.get('automator')
    if automator: automator.close()
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOTFATHER_TOKEN_HERE":
        logger.error("BOT_TOKEN is not configured.")
        print("ERROR: Open this file and replace PASTE_YOUR_BOTFATHER_TOKEN_HERE with your BotFather token.")
        return

    # Android/Pydroid does not use the Linux path /usr/bin/google-chrome.
    # Browser availability is checked when OnamAutomator is actually created.

    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        logger.exception("Telegram application initialization failed")
        print(f"ERROR: Telegram bot initialization failed: {e}")
        return
    
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🚀 Start Claim$"), claim_start),
            MessageHandler(filters.Regex("^➕ New Entry$"), claim_start)
        ],
        states={
            VOUCHER: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ Cancel$"), get_voucher)],
            MOBILE: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ Cancel$"), get_mobile)],
            OTP: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ Cancel$"), get_otp)],
            UPI: [MessageHandler(filters.TEXT & ~filters.Regex("^❌ Cancel$"), get_upi)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), cancel), CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    print("🚀 Ultra-Fast Bot is running...")
    application.run_polling()

if __name__ == "__main__": main()
                
