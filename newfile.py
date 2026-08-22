# ====================================================
#               MADE BY XPILIOT
#     PRIME HOSTING SERVER v4.5 (RAILWAY READY)
# ====================================================

import os
import sys
import sqlite3
import subprocess
import time
import random
import string
import re
import threading
from datetime import datetime, timedelta
from telebot import TeleBot, types

# ==================== RAILWAY CONFIGURATION ====================
# Railway Variables se Token aur IDs uthayega, agar nahi mile toh default use karega (Local ke liye)
# ==================== RAILWAY CONFIGURATION ====================
# Railway Variables se Token aur IDs uthayega, agar nahi mile toh default use karega (Local ke liye)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8860367736:AAGjQhG_BwAqhIStk1PMP-40aM-9WxUXcVw")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "xpliot_bot")         # <-- CHANGE (Bot ka username)
ADMIN_ID = int(os.environ.get("ADMIN_ID", 672211281))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Xpiliotraj")      # <-- CHANGE (Aapka Telegram ID)

HOST_DIR = "hosted_files"
MAX_LOG_SIZE_MB = 5

# Default Values (User can change via Bot)
config = {
    "upi_id": "raj42006@fam",
    "price_amount": 99,
    "price_days": 30,
    "free_limit": 2,
    "prime_limit": 5
}

os.makedirs(HOST_DIR, exist_ok=True)

# ⚡ Multi-Threaded Bot Instance
bot = TeleBot(BOT_TOKEN, threaded=True, num_threads=50)

# ==================== DATABASE SETUP ====================
def get_db():
    conn = sqlite3.connect("hosting_data.db", check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_prime INTEGER DEFAULT 0,
            prime_expire TEXT DEFAULT NULL,
            referred_by INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0
        )
    """)
    # BOTS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            filepath TEXT,
            logpath TEXT,
            pid INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'stopped',
            auto_guard INTEGER DEFAULT 1,
            speed_boost INTEGER DEFAULT 0
        )
    """)
    # CODES TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prime_codes (
            code TEXT PRIMARY KEY,
            days INTEGER
        )
    """)
    # CONFIG TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert default config values if not exists
    default_config = {
        "upi_id": "raj42006@fam",
        "price_amount": "99",
        "price_days": "30",
        "free_limit": "2",
        "prime_limit": "5"
    }
    for k, v in default_config.items():
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    
    conn.commit()
    conn.close()

init_db()

# ==================== LOAD & RELOAD CONFIG ====================
def load_config():
    global config
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM config")
    rows = cursor.fetchall()
    conn.close()
    for row in rows:
        if row['key'] in config:
            if row['key'] in ["price_amount", "price_days", "free_limit", "prime_limit"]:
                config[row['key']] = int(row['value'])
            else:
                config[row['key']] = row['value']

# Load config on start
load_config()

# ==================== HELPER FUNCTIONS ====================
def register_user(user_id, ref_by=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        if ref_by and ref_by != user_id:
            cursor.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, ref_by))
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (ref_by,))
            cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (ref_by,))
            ref_row = cursor.fetchone()
            if ref_row and ref_row['referral_count'] % 3 == 0:
                add_prime_days(ref_by, 1)
                try:
                    bot.send_message(ref_by, "🎉 **Referral Bonus!** Received 1 day of FREE Prime VIP access.")
                except Exception:
                    pass
        else:
            cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    conn.close()

def is_prime_user(user_id):
    # Prime VIP is free for everyone now.
    return True

def add_prime_days(user_id, days):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT prime_expire FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    now = datetime.now()
    if row and row['prime_expire']:
        try:
            current_expire = datetime.strptime(row['prime_expire'], "%Y-%m-%d %H:%M:%S")
            new_expire = (current_expire if current_expire > now else now) + timedelta(days=days)
        except Exception:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)
        
    expire_str = new_expire.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET is_prime = 1, prime_expire = ? WHERE user_id = ?", (expire_str, user_id))
    conn.commit()
    conn.close()

def send_or_edit(chat_id, text, reply_markup=None, message_id=None, parse_mode="Markdown"):
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)

# ==================== CRASH GUARD WORKER ====================
def is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def crash_guard_worker():
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hosted_bots WHERE status = 'running'")
            running_bots = cursor.fetchall()
            
            for b in running_bots:
                pid = b['pid']
                bot_id = b['id']
                user_id = b['user_id']
                filepath = b['filepath']
                logpath = b['logpath']
                
                if os.path.exists(logpath) and os.path.getsize(logpath) > MAX_LOG_SIZE_MB * 1024 * 1024:
                    try:
                        with open(logpath, 'w', encoding='utf-8') as f:
                            f.write(f"--- [LOG RESET AT {datetime.now()}] ---\n")
                    except Exception:
                        pass

                is_alive = False
                if pid:
                    is_alive = is_process_alive(pid)
                
                if not is_alive:
                    if is_prime_user(user_id) and b['auto_guard'] == 1:
                        try:
                            log_file = open(logpath, 'a', encoding='utf-8')
                            log_file.write(f"\n--- [AUTO RESTART AT {datetime.now()}] ---\n")
                            log_file.flush()
                            
                            proc = subprocess.Popen(
                                [sys.executable, "-u", filepath],
                                stdout=log_file,
                                stderr=log_file,
                                cwd=os.path.dirname(filepath)
                            )
                            log_file.close()
                            cursor.execute("UPDATE hosted_bots SET pid = ? WHERE id = ?", (proc.pid, bot_id))
                            conn.commit()
                        except Exception:
                            cursor.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
                            conn.commit()
                    else:
                        cursor.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
                        conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(10)

guard_thread = threading.Thread(target=crash_guard_worker, daemon=True)
guard_thread.start()

# ==================== KEYBOARDS ====================
def main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Upload Bot (.py)", callback_data="upload_info"),
        types.InlineKeyboardButton("📱 My Hosted Bots", callback_data="my_bots")
    )
    markup.add(types.InlineKeyboardButton("💎 PRIME VIP ZONE 🌟", callback_data="prime_zone"))
    markup.add(
        types.InlineKeyboardButton("👥 Referral Program", callback_data="referral_info"),
        types.InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="claim_code")
    )
    markup.add(
        types.InlineKeyboardButton("📊 Server Status", callback_data="server_stats"),
        types.InlineKeyboardButton("❓ Help & Guide", callback_data="help_guide")
    )
    markup.add(
        types.InlineKeyboardButton("📞 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")
    )
    if user_id == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("⚙️ Admin Control Panel", callback_data="admin_panel"))
    return markup

def prime_zone_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🛒 BUY PRIME VIP 🛒", callback_data="buy_prime"))
    markup.add(
        types.InlineKeyboardButton("⏳ Subscription Status", callback_data="prime_expire_check"),
        types.InlineKeyboardButton("🎁 Gift Prime to Friend", callback_data="gift_prime")
    )
    markup.add(
        types.InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="claim_code"),
        types.InlineKeyboardButton("💳 Payment Info", callback_data="pay_info")
    )
    markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return markup

def admin_panel_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Change Price/Days", callback_data="admin_change_price"),
        types.InlineKeyboardButton("📲 Change UPI ID", callback_data="admin_change_upi")
    )
    markup.add(
        types.InlineKeyboardButton("📦 Change Bot Limits", callback_data="admin_change_limits"),
        types.InlineKeyboardButton("🔄 Reload Config", callback_data="admin_reload")
    )
    markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return markup

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    ref_by = None
    
    text_args = message.text.split()
    if len(text_args) > 1 and text_args[1].startswith("ref_"):
        try:
            ref_by = int(text_args[1].replace("ref_", ""))
        except ValueError:
            pass

    register_user(user_id, ref_by)
    is_prime = is_prime_user(user_id)
    user_name = message.from_user.first_name or "User"

    badge = "👑 PRIME VIP MEMBER" if is_prime else "FREE STANDARD USER"
    limit_info = f"🚀 Hosting Limit: {config['prime_limit']} Bots" if is_prime else f"📦 Hosting Limit: {config['free_limit']} Bot"

    welcome_msg = (
        f"🎬 **Made by Xpiliot** 🎬\n"
        f"👑 **PRIME HOSTING SERVER v4.5** 👑\n\n"
        f"✨ **Welcome, {user_name}!**\n\n"
        f"👤 **User Profile Card:**\n"
        f" ├ 🏷️ **Name:** `{user_name}`\n"
        f" ├ 🆔 **User ID:** `{user_id}`\n"
        f" └ 💎 **Status:** **{badge}**\n\n"
        f"⚡ **Services:**\n"
        f" ├ {limit_info}\n"
        f" └ 🛡️ **Crash Guard:** {'24/7 Enabled' if is_prime else 'Prime Only'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 **Select an option below:**"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    register_user(user_id)
    
    if not message.document.file_name or not message.document.file_name.endswith('.py'):
        bot.reply_to(message, "❌ **Invalid File Format!** Please upload a `.py` Python script only.")
        return

    is_prime = is_prime_user(user_id)
    max_allowed = config['prime_limit'] if is_prime else config['free_limit']
    filename = message.document.file_name

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM hosted_bots WHERE user_id = ? AND filename = ?", (user_id, filename))
    existing_bot = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as count FROM hosted_bots WHERE user_id = ?", (user_id,))
    current_count = cursor.fetchone()['count']

    if not existing_bot and current_count >= max_allowed:
        conn.close()
        bot.reply_to(message, f"⚠️ **Limit Reached!** You can host max {max_allowed} bot(s). Upgrade to Prime VIP for more.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    user_dir = os.path.join(os.getcwd(), HOST_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    filepath = os.path.join(user_dir, filename)
    logpath = filepath + ".log"

    with open(filepath, 'wb') as new_file:
        new_file.write(downloaded_file)

    if existing_bot:
        cursor.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (existing_bot['id'],))
    else:
        cursor.execute("INSERT INTO hosted_bots (user_id, filename, filepath, logpath, status) VALUES (?, ?, ?, ?, 'stopped')", 
                       (user_id, filename, filepath, logpath))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"✅ **{filename}** saved successfully!\n\n📱 Click 'My Hosted Bots' to control it.")

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "main_menu":
        send_or_edit(chat_id, "🏠 **Main Navigation Menu:**", main_menu_keyboard(user_id), msg_id)

    elif call.data == "prime_zone":
        msg = (
            f"👑 **PRIME VIP ZONE** 👑\n"
            f"🎬 *Made by Xpiliot*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Your Status:** 👑 PRIME VIP MEMBER (Free for everyone!)\n\n"
            f"🔥 **Prime Features:**\n"
            f" ├ 🚀 Host up to {config['prime_limit']} Bots\n"
            f" ├ ⚡ High Priority Execution\n"
            f" ├ 🛡️ Auto Crash Guard (Auto-restart)\n"
            f" └ 🎧 VIP Support\n\n"
            f"💰 **Price:** FREE 🎉"
        )
        send_or_edit(chat_id, msg, prime_zone_keyboard(), msg_id)

    elif call.data == "buy_prime":
        msg = (
            f"🎉 **PRIME VIP IS FREE FOR EVERYONE!**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"No payment needed — every user automatically has full Prime VIP access.\n\n"
            f"🔥 Enjoy all Prime features right away!"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Prime Zone", callback_data="prime_zone"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "pay_info":
        msg = (
            f"🎉 **PRIME VIP IS FREE FOR EVERYONE!**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"No payment or manual verification needed — everyone already has Prime VIP access."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Prime Zone", callback_data="prime_zone"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "prime_expire_check":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT prime_expire FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if is_prime_user(user_id):
            expire_str = row['prime_expire'] if row and row['prime_expire'] else "Unlimited (Admin)"
            msg = f"🌟 **Your Prime VIP is Active!**\n⏳ **Expires on:** `{expire_str}`"
        else:
            msg = "❌ **You do not have an active Prime VIP subscription.**"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Prime Zone", callback_data="prime_zone"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "gift_prime":
        if not is_prime_user(user_id):
            bot.send_message(chat_id, "❌ Only Prime VIP members can gift access!")
            return
        m = bot.send_message(chat_id, "🎁 **Enter target user's Numeric Telegram ID:**")
        bot.register_next_step_handler(m, process_gift_prime)

    elif call.data == "upload_info":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, "📥 **Please send your `.py` Python file directly into this chat.**", markup, msg_id)

    elif call.data == "referral_info":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        ref_count = row['referral_count'] if row else 0
        conn.close()

        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        msg = (
            f"👥 **Referral Program**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Invite friends to get FREE Prime VIP!\n\n"
            f"🔗 **Your Link:**\n`{ref_link}`\n\n"
            f"📊 **Referrals:** `{ref_count}` user(s)\n"
            f"🎁 **Reward:** 1 day FREE Prime VIP per 3 invites."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "server_stats":
        cpu_info = "Not Available (Android)"
        ram_info = "Not Available (Android)"
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM hosted_bots")
        total_bots = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as running FROM hosted_bots WHERE status='running'")
        running_bots = cursor.fetchone()['running']
        conn.close()

        msg = (
            f"🖥️ **Server Real-time Status**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 **CPU:** `{cpu_info}` | 💾 **RAM:** `{ram_info}`\n"
            f"🤖 **Total Bots:** `{total_bots}`\n"
            f"🟢 **Running Bots:** `{running_bots}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh Status", callback_data="server_stats"))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "help_guide":
        help_msg = (
            f"❓ **Help & Guide**\n\n"
            f"1️⃣ Upload `.py` file.\n"
            f"2️⃣ Go to **My Hosted Bots**.\n"
            f"3️⃣ Press ▶️ **Start Bot**.\n"
            f"4️⃣ Check **Live Logs** if errors occur."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, help_msg, markup, msg_id)

    elif call.data == "claim_code":
        m = bot.send_message(chat_id, "🎟️ **Enter your Prime Coupon Code:**")
        bot.register_next_step_handler(m, process_claim_code)

    # ==================== DYNAMIC ADMIN PANEL ACTIONS ====================
    elif call.data == "admin_panel":
        if user_id != ADMIN_ID: return
        msg = (
            f"⚙️ **ADMIN CONTROL PANEL** ⚙️\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🛠️ **Current Settings:**\n"
            f"💰 Price: ₹{config['price_amount']} / {config['price_days']} Days\n"
            f"📲 UPI ID: `{config['upi_id']}`\n"
            f"📦 Free Limit: {config['free_limit']} | 👑 Prime Limit: {config['prime_limit']}\n\n"
            f"👇 **Select an option to change:**"
        )
        send_or_edit(chat_id, msg, admin_panel_keyboard(), msg_id)

    elif call.data == "admin_change_price":
        if user_id != ADMIN_ID: return
        m = bot.send_message(chat_id, "✏️ **Enter new Price Amount (Numbers only):**\n*(Example: `149`)*")
        bot.register_next_step_handler(m, process_admin_set_price)

    elif call.data == "admin_change_upi":
        if user_id != ADMIN_ID: return
        m = bot.send_message(chat_id, "✏️ **Enter new UPI ID:**\n*(Example: `yourname@paytm`)*")
        bot.register_next_step_handler(m, process_admin_set_upi)

    elif call.data == "admin_change_limits":
        if user_id != ADMIN_ID: return
        m = bot.send_message(chat_id, "✏️ **Enter new limits (Free, Prime):**\n*(Example: `3, 10`)*\n-> Free limit 3, Prime limit 10")
        bot.register_next_step_handler(m, process_admin_set_limits)

    elif call.data == "admin_reload":
        if user_id != ADMIN_ID: return
        load_config()
        bot.send_message(chat_id, "✅ **Configuration Reloaded Successfully!**")

    elif call.data == "my_bots":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hosted_bots WHERE user_id = ?", (user_id,))
        bots = cursor.fetchall()
        conn.close()

        if not bots:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
            send_or_edit(chat_id, "❌ **No uploaded bots found.**", markup, msg_id)
            return

        markup = types.InlineKeyboardMarkup()
        for b in bots:
            icon = "🟢" if (b['status'] == 'running' and b['pid'] and is_process_alive(b['pid'])) else "🔴"
            markup.add(types.InlineKeyboardButton(f"{icon} {b['filename']}", callback_data=f"manage_{b['id']}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, "⚙️ **Select a bot to manage:**", markup, msg_id)

    elif call.data.startswith("manage_"):
        bot_id = int(call.data.split("_")[1])
        render_bot_control(chat_id, bot_id, msg_id)

    elif call.data.startswith("startbot_"):
        bot_id = int(call.data.split("_")[1])
        start_bot_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("stopbot_"):
        bot_id = int(call.data.split("_")[1])
        stop_bot_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("logbot_"):
        bot_id = int(call.data.split("_")[1])
        show_logs_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("clearlog_"):
        bot_id = int(call.data.split("_")[1])
        clear_logs_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("piplist_"):
        bot_id = int(call.data.split("_")[1])
        show_pip_action(chat_id, bot_id, msg_id)

    elif call.data.startswith("pipinstall_"):
        bot_id = int(call.data.split("_")[1])
        m = bot.send_message(
            chat_id,
            "📦 **Send package name(s) to install.**\n\n"
            "Examples:\n"
            "`requests`\n"
            "`requests flask`\n"
            "`python-telegram-bot==22.0`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(m, process_pip_install, bot_id)

    elif call.data.startswith("delbot_"):
        bot_id = int(call.data.split("_")[1])
        delete_bot_action(chat_id, bot_id, msg_id)

# ==================== ADMIN STEP PROCESSORS ====================
def process_admin_set_price(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        val = int(message.text.strip())
        conn = get_db()
        conn.execute("UPDATE config SET value = ? WHERE key = 'price_amount'", (str(val),))
        conn.commit()
        conn.close()
        load_config()
        bot.reply_to(message, f"✅ **Price changed to ₹{val} successfully!**")
    except ValueError:
        bot.reply_to(message, "❌ **Invalid number!** Please send only digits.")

def process_admin_set_upi(message):
    if message.from_user.id != ADMIN_ID: return
    val = message.text.strip()
    if "@" not in val:
        bot.reply_to(message, "❌ **Invalid UPI ID!** It must contain '@' (e.g., name@upi).")
        return
    conn = get_db()
    conn.execute("UPDATE config SET value = ? WHERE key = 'upi_id'", (val,))
    conn.commit()
    conn.close()
    load_config()
    bot.reply_to(message, f"✅ **UPI ID changed to `{val}` successfully!**", parse_mode="Markdown")

def process_admin_set_limits(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.strip().split(",")
        if len(parts) != 2:
            raise ValueError
        free = int(parts[0].strip())
        prime = int(parts[1].strip())
        
        conn = get_db()
        conn.execute("UPDATE config SET value = ? WHERE key = 'free_limit'", (str(free),))
        conn.execute("UPDATE config SET value = ? WHERE key = 'prime_limit'", (str(prime),))
        conn.commit()
        conn.close()
        load_config()
        bot.reply_to(message, f"✅ **Limits Updated!**\n📦 Free: {free} | 👑 Prime: {prime}")
    except Exception:
        bot.reply_to(message, "❌ **Invalid format!** Use: `FreeLimit, PrimeLimit`\nExample: `3, 10`")

# ==================== BOT CONTROL ACTIONS ====================
def render_bot_control(chat_id, bot_id, msg_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if not b:
        bot.send_message(chat_id, "❌ Bot process not found.")
        return

    is_running = False
    if b['status'] == 'running' and b['pid'] and is_process_alive(b['pid']):
        is_running = True

    status_icon = "🟢 Running" if is_running else "🔴 Stopped"

    msg = (
        f"🤖 **Bot Control Panel**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📄 **File:** `{b['filename']}`\n"
        f"📊 **Status:** {status_icon}\n"
        f"🆔 **PID:** `{b['pid'] if is_running else 'N/A'}`\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(types.InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stopbot_{b['id']}"))
    else:
        markup.add(types.InlineKeyboardButton("▶️ Start Bot", callback_data=f"startbot_{b['id']}"))

    markup.add(
        types.InlineKeyboardButton("📜 Live Logs", callback_data=f"logbot_{b['id']}"),
        types.InlineKeyboardButton("🧹 Clear Logs", callback_data=f"clearlog_{b['id']}")
    )
    markup.add(
        types.InlineKeyboardButton("📋 Pip Packages", callback_data=f"piplist_{b['id']}"),
        types.InlineKeyboardButton("📦 Install Package", callback_data=f"pipinstall_{b['id']}")
    )
    markup.add(types.InlineKeyboardButton("🔄 Refresh Panel", callback_data=f"manage_{b['id']}"))
    markup.add(types.InlineKeyboardButton("🗑️ Delete Bot", callback_data=f"delbot_{b['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))

    send_or_edit(chat_id, msg, markup, msg_id)

def start_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b and (not b['pid'] or not is_process_alive(b['pid'])):
        try:
            log_file = open(b['logpath'], 'a', encoding='utf-8')
            process = subprocess.Popen(
                [sys.executable, "-u", b['filepath']],
                stdout=log_file,
                stderr=log_file,
                cwd=os.path.dirname(b['filepath'])
            )
            log_file.close()
            cursor.execute("UPDATE hosted_bots SET status = 'running', pid = ? WHERE id = ?", (process.pid, bot_id))
            conn.commit()
        except Exception:
            pass
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def stop_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b and b['pid']:
        try:
            if is_process_alive(b['pid']):
                os.kill(b['pid'], 9)
        except Exception:
            pass

    cursor.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def show_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if not b or not os.path.exists(b['logpath']):
        bot.send_message(chat_id, "❌ Log file missing.")
        return

    try:
        with open(b['logpath'], 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = "".join(lines[-35:])
            
        if not last_lines.strip():
            last_lines = "No logs recorded yet."

        msg = f"📜 **Live Logs for `{b['filename']}`:**\n```\n{last_lines[:3500]}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Refresh Logs", callback_data=f"logbot_{bot_id}"),
            types.InlineKeyboardButton("🧹 Clear Logs", callback_data=f"clearlog_{bot_id}")
        )
        markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: `{str(e)}`")

def clear_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT logpath FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if b and os.path.exists(b['logpath']):
        try:
            with open(b['logpath'], 'w', encoding='utf-8') as f:
                f.write("")
        except Exception:
            pass
    show_logs_action(chat_id, bot_id, msg_id)

def show_pip_action(chat_id, bot_id, msg_id):
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
        packages = res.stdout[:3000]
        msg = f"📋 **Installed Python Packages:**\n```\n{packages}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: `{str(e)}`")

def process_pip_install(message, bot_id):
    """Install packages for a hosted bot, including on Pydroid.

    Important: never rely on the broken `python -m pip` entry point.
    First try Pydroid's own bundled pip executable, then the normal
    pip executables, and finally bootstrap pip using ensurepip.
    """
    raw = (message.text or "").strip()

    if not raw:
        bot.reply_to(message, "❌ Send at least one package name.")
        return

    # Don't execute shell commands. Only allow normal pip requirement characters.
    if len(raw) > 500 or raw.startswith("-") or any(
        c in raw for c in [";", "&", "|", "`", "$", ">", "<", "\\", "\n", "\r"]
    ):
        bot.reply_to(message, "❌ Invalid package input.")
        return

    # Split multiple simple requirements.
    packages = raw.split()
    try:
        allowed = re.compile(r"^[A-Za-z0-9_.-]+(?:[<>=!~]{1,2}[A-Za-z0-9*_.+-]+)?$")
    except Exception:
        bot.reply_to(message, "❌ Package validation could not be initialized.")
        return

    if not all(allowed.fullmatch(p) for p in packages):
        bot.reply_to(
            message,
            "❌ Invalid package format.\nUse names like `requests` or `flask==3.1.0`."
        )
        return

    # Verify the hosted bot exists.
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    hosted = cursor.fetchone()
    conn.close()

    if not hosted:
        bot.reply_to(message, "❌ Hosted bot not found.")
        return

    bot.reply_to(
        message,
        "⏳ Installing:\n" + "\n".join(f"• `{p}`" for p in packages),
        parse_mode="Markdown"
    )

    def run(cmd):
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

    output_parts = []
    success = False

    # Pydroid normally provides its own pip executable. Prefer it.
    candidates = []

    pydroid_bin = os.path.dirname(sys.executable)
    candidates.extend([
        os.path.join(pydroid_bin, "pip3"),
        os.path.join(pydroid_bin, "pip"),
    ])

    import shutil
    candidates.extend([
        shutil.which("pip3"),
        shutil.which("pip"),
    ])

    # Remove duplicates/nonexistent paths.
    seen = set()
    candidates = [
        p for p in candidates
        if p and p not in seen and not seen.add(p) and os.path.exists(p)
    ]

    # First try the executable directly.
    for pip_exe in candidates:
        try:
            result = run([pip_exe, "install", "--disable-pip-version-check", *packages])
            out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            output_parts.append(f"$ {pip_exe} install ...\n{out[-2500:]}")
            if result.returncode == 0:
                success = True
                break
        except Exception as e:
            output_parts.append(f"$ {pip_exe}\n{e}")

    # If pip executable is broken, try ensurepip to repair/rebuild pip.
    if not success:
        try:
            ensure = run([sys.executable, "-m", "ensurepip", "--upgrade"])
            out = ((ensure.stdout or "") + "\n" + (ensure.stderr or "")).strip()
            output_parts.append(f"$ ensurepip --upgrade\n{out[-2000:]}")
        except Exception as e:
            output_parts.append(f"$ ensurepip\n{e}")

        # Retry pip after ensurepip.
        for pip_exe in candidates:
            try:
                result = run([pip_exe, "install", "--disable-pip-version-check", *packages])
                out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                output_parts.append(f"$ retry {pip_exe}\n{out[-2500:]}")
                if result.returncode == 0:
                    success = True
                    break
            except Exception as e:
                output_parts.append(f"$ retry {pip_exe}\n{e}")

    # Last normal fallback.
    if not success:
        try:
            result = run([
                sys.executable, "-m", "pip",
                "install", "--disable-pip-version-check", *packages
            ])
            out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            output_parts.append(f"$ python -m pip\n{out[-2500:]}")
            success = result.returncode == 0
        except Exception as e:
            output_parts.append(f"$ python -m pip\n{e}")

    final_output = "\n\n".join(output_parts)[-6500:]

    if success:
        header = "✅ **Package installation completed.**"
    else:
        header = (
            "❌ **Pip could not install the package.**\n\n"
            "This can happen when Pydroid's pip is damaged or the package "
            "has no compatible Android/Python 3.13 build."
        )

    # Telegram limits text messages to 4096 characters. Send the result
    # in small chunks so long pip output never causes another 400 error.
    output_text = final_output or "No pip output was returned."
    chunks = [output_text[i:i + 3000] for i in range(0, len(output_text), 3000)]

    try:
        bot.send_message(message.chat.id, header, parse_mode="Markdown")
        for chunk in chunks:
            # Plain text avoids Markdown parse errors from pip output.
            bot.send_message(
                message.chat.id,
                f"```text\n{chunk}\n```",
                parse_mode="Markdown"
            )
    except Exception as e:
        # Last-resort short reply, so the user always gets a response.
        try:
            bot.send_message(
                message.chat.id,
                f"⚠️ Installation finished, but the output could not be sent.\nError: {str(e)[:500]}"
            )
        except Exception:
            pass


def delete_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, logpath, pid FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b:
        if b['pid'] and is_process_alive(b['pid']):
            try:
                os.kill(b['pid'], 9)
            except Exception:
                pass
        if os.path.exists(b['filepath']): 
            try: os.remove(b['filepath'])
            except Exception: pass
        if os.path.exists(b['logpath']): 
            try: os.remove(b['logpath'])
            except Exception: pass

    cursor.execute("DELETE FROM hosted_bots WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))
    send_or_edit(chat_id, "🗑️ **Bot script and logs deleted successfully.**", markup, msg_id)

# ==================== USER STEP PROCESSORS ====================
def process_claim_code(message):
    if not message.text:
        bot.reply_to(message, "❌ **Invalid input!** Please send text coupon code.")
        return
    code_input = message.text.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prime_codes WHERE code = ?", (code_input,))
    row = cursor.fetchone()

    if row:
        add_prime_days(message.from_user.id, row['days'])
        cursor.execute("DELETE FROM prime_codes WHERE code = ?", (code_input,))
        conn.commit()
        bot.reply_to(message, f"🎉 **Activated {row['days']} days of Prime VIP!**")
    else:
        bot.reply_to(message, "❌ **Invalid code!**")
    conn.close()

def process_gift_prime(message):
    if not message.text or not message.text.isdigit():
        bot.reply_to(message, "❌ **Invalid Telegram Numeric ID.**")
        return
    try:
        friend_id = int(message.text.strip())
        add_prime_days(friend_id, 7)
        bot.reply_to(message, f"🎁 **Gifted 7 days Prime VIP to `{friend_id}`!**")
    except Exception:
        bot.reply_to(message, "❌ **An error occurred.**")

@bot.message_handler(commands=['genkey'])
def gen_key_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        days = int(message.text.split()[1])
    except Exception:
        days = 30
    code = "PRIME-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO prime_codes (code, days) VALUES (?, ?)", (code, days))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🎟️ **Prime Code Generated:**\n`{code}` ({days} Days)", parse_mode="Markdown")

# ==================== HIGH PERFORMANCE POLLING ====================
if __name__ == '__main__':
    print("🎬 Made by Xpiliot")
    print("⚡ Ultra-Fast Prime Hosting Server v4.5 Running...")
    print(f"✅ Bot Username: @{BOT_USERNAME}")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ UPI ID: {config['upi_id']}")
    print(f"✅ Price: ₹{config['price_amount']} / {config['price_days']} Days")
    
    bot.infinity_polling(
        skip_pending=True,
        timeout=10,
        long_polling_timeout=5
    )