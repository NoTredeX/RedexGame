import logging
import uuid
import os
import mysql.connector
import requests
import re
import fcntl
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# تنظیم لاگ‌گیری
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler('bot.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

load_dotenv()

ADMIN_ID = os.getenv("ADMIN_ID", "1631919159")
IPDNS1 = os.getenv("IPDNS1")
IPDNS2 = os.getenv("IPDNS2")
SERVER_IP = "game.redexping.tech"
CARD_NUMBER = "1234-5678-9012-3456"

def acquire_lock():
    lock_file = '/tmp/bot.lock'
    fd = open(lock_file, 'w')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.debug("Acquired bot lock")
        return fd
    except IOError:
        logger.error("Another instance of the bot is already running")
        sys.exit(1)

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=3307,
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD"),
            database="dnsbot",
            autocommit=True
        )
        logger.debug("Successfully connected to database with autocommit=True")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        return None

def is_iranian_ip(ip):
    try:
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()
        logger.debug(f"IP check response for {ip}: {data}")
        return data.get("country_code") == "IR"
    except requests.RequestException as e:
        logger.error(f"Error checking IP with ipapi.co: {e}")
        return False

def generate_random_name(telegram_id, username):
    base_name = username.lstrip('@') if username else f"user_{telegram_id}"
    return f"{base_name}_{str(uuid.uuid4())[:8]}"

def escape_markdown_v2(text):
    """Escape special characters for MarkdownV2."""
    if not text:
        return text
    special_chars = r'[_*[\]()~`>#+-=|{}.!]'
    return re.sub(special_chars, r'\\\g<0>', text)

def check_expired_services(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to check expired services: DB connection failed")
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE services SET status = 'expired', ip_address = NULL WHERE expiry_date <= NOW() AND status = 'active' AND deleted = FALSE"
        )
        cursor.execute(
            "DELETE FROM services WHERE status = 'expired' AND expiry_date <= %s AND deleted = FALSE AND is_test = FALSE",
            (datetime.now() - timedelta(days=7),)
        )
        cursor.execute(
            "SELECT service_id, telegram_id, name, is_test FROM services WHERE status = 'expired' AND deleted = FALSE"
        )
        expired_services = cursor.fetchall()
        for service_id, telegram_id, name, is_test in expired_services:
            if is_test:
                keyboard = [[InlineKeyboardButton("🛒 خرید سرویس جدید", callback_data="buy_new_service")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"🧪 سرویس تست شما ({name}) منقضی شد! ⏳ لطفاً برای ادامه، سرویس جدیدی خریداری کنید:",
                    reply_markup=reply_markup
                )
            logger.debug(f"Expired service {service_id} for user {telegram_id}")
        logger.debug(f"Checked expired services, found {len(expired_services)}")
    except mysql.connector.Error as e:
        logger.error(f"Error checking expired services: {e}")
    finally:
        cursor.close()
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    logger.debug(f"User {user_id} started the bot")
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT IGNORE INTO users (telegram_id) VALUES (%s)", (user_id,))
            logger.debug(f"User {user_id} added to database")
        except mysql.connector.Error as e:
            logger.error(f"Database error in start: {e}")
        finally:
            cursor.close()
            conn.close()
    keyboard = [
        [InlineKeyboardButton("📋 سرویس‌های من", callback_data="my_services")],
        [InlineKeyboardButton("🛒 خرید سرویس جدید", callback_data="buy_new_service")],
        [InlineKeyboardButton("🧪 تست رایگان", callback_data="get_test")],
        [InlineKeyboardButton("🌐 تنظیمات DNS", callback_data="dns_servers")],
        [InlineKeyboardButton("📚 آموزش‌ها", callback_data="tutorials")],
        [InlineKeyboardButton("❓ سوالات متداول", callback_data="faq")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📊 آمار کاربران", callback_data="stats")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        text="•.¸♡ به ربات ردکس گیم خوش اومدی ♡¸.•\n🚀 با DNS اختصاصی ما از بازی کردن لذت ببر 🚀",
        reply_markup=reply_markup,
        reply_to_message_id=update.message.message_id
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} accessed main_menu")
    keyboard = [
        [InlineKeyboardButton("📋 سرویس‌های من", callback_data="my_services")],
        [InlineKeyboardButton("🛒 خرید سرویس جدید", callback_data="buy_new_service")],
        [InlineKeyboardButton("🧪 تست رایگان", callback_data="get_test")],
        [InlineKeyboardButton("🌐 تنظیمات DNS", callback_data="dns_servers")],
        [InlineKeyboardButton("📚 آموزش‌ها", callback_data="tutorials")],
        [InlineKeyboardButton("❓ سوالات متداول", callback_data="faq")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📊 آمار کاربران", callback_data="stats")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.message.edit_text(
            text="•.¸♡ به ربات ردکس گیم خوش اومدی ♡¸.•\nلطفاً گزینه مورد نظر خود را انتخاب کنید: 🚀",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error editing main_menu: {e}")
        await query.message.reply_text(
            text="•.¸♡ به ربات ردکس گیم خوش اومدی ♡¸.•\nلطفاً گزینه مورد نظر خود را انتخاب کنید: 🚀",
            reply_markup=reply_markup
        )

async def my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} accessed my_services")
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in my_services")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_id, name, status, is_test FROM services WHERE telegram_id = %s AND deleted = FALSE",
            (user_id,)
        )
        services = cursor.fetchall()
        logger.debug(f"Found {len(services)} services for user {user_id}: {services}")
        if not services:
            keyboard = [
                [InlineKeyboardButton("🛒 خرید سرویس جدید", callback_data="buy_new_service")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(
                text="📭 هنوز هیچ سرویسی ثبت نکرده‌اید! لطفاً سرویس جدیدی خریداری کنید یا به منوی اصلی بازگردید:",
                reply_markup=reply_markup
            )
            return
        keyboard = [
            [InlineKeyboardButton(f"{name} {'🧪' if is_test else ''} {'✅' if status == 'active' else '⏳'}", callback_data=f"service_info_{service_id}")]
            for service_id, name, status, is_test in services
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            text="📋 لیست سرویس‌های شما:",
            reply_markup=reply_markup
        )
    except mysql.connector.Error as e:
        logger.error(f"Database error in my_services: {e}")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()

async def service_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split("_")[2]
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} accessed service_info for service {service_id}")
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in service_info")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, ip_address, purchase_date, expiry_date, status, is_test FROM services WHERE service_id = %s AND telegram_id = %s AND deleted = FALSE",
            (service_id, user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Service {service_id} not found for user {user_id}")
            await query.message.edit_text(
                text="🚫 سرویس مورد نظر یافت نشد!"
            )
            return
        name, ip_address, purchase_date, expiry_date, status, is_test = result
        remaining_days = max((expiry_date - datetime.now()).days, 0) if status == "active" else 0
        status_text = "✅" if status == "active" else "⏳"
        ip_text = ip_address or "ثبت نشده"
        purchase_date_str = purchase_date.strftime('%Y-%m-%d')
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        logger.debug(f"Service info: name={name}, ip={ip_text}, status={status_text}")
        keyboard = [
            [InlineKeyboardButton(f"📍 ثبت {'آی‌پی' if not ip_address else 'آی‌پی جدید'}", callback_data=f"register_ip_{service_id}")]
        ]
        if not is_test:
            keyboard.append([InlineKeyboardButton("🔄 تمدید سرویس", callback_data=f"renew_service_{service_id}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="my_services")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            text=(
                f"📋 اطلاعات سرویس:\n"
                f"نام سرویس: {name}\n"
                f"نوع: {'🧪 تست' if is_test else '💳 خریداری‌شده'}\n"
                f"📅 تاریخ خرید: {purchase_date_str}\n"
                f"📆 تاریخ انقضا: {expiry_date_str}\n"
                f"⏰ زمان باقی‌مانده: {remaining_days} روز\n"
                f"🌐 آی‌پی: {ip_text}\n"
                f"وضعیت: {status_text}"
            ),
            reply_markup=reply_markup
        )
    except mysql.connector.Error as e:
        logger.error(f"Database error in service_info: {e}")
        await query.message.edit_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in service_info: {e}")
        await query.message.edit_text(
            text="⚠️ خطای غیرمنتظره‌ای رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()

async def register_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split("_")[2]
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} requested to register IP for service {service_id}")
    web_app_url = f"https://{SERVER_IP}/register/{service_id}/{user_id}"
    keyboard = [
        [InlineKeyboardButton("📍 ثبت خودکار آی‌پی", url=web_app_url)],
        [InlineKeyboardButton("✍️ ثبت دستی آی‌پی", callback_data=f"manual_ip_{service_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"service_info_{service_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text="📡 نحوه ثبت آی‌پی خود را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def manual_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split("_")[2]
    user_id = str(query.from_user.id)
    context.user_data["service_id"] = service_id
    context.user_data["telegram_id"] = user_id
    context.user_data["state"] = "awaiting_ip"
    logger.debug(f"User {user_id} entered manual_ip for service {service_id}")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"service_info_{service_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=(
            "✍️ لطفاً آی‌پی خود را در پیام بعدی ارسال کنید.\n"
            "در صورت نداشتن اطلاعات آی‌پی، از طریق لینک زیر آن را دریافت کنید:\n"
            "🔗 https://ipgeolocation.io/what-is-my-ip\n"
            "⚠️ آی‌پی را بدون https:// یا / وارد کنید.\n\n"
            "📌 پیشنهاد می‌شود از گزینه ثبت خودکار آی‌پی استفاده کنید."
        ),
        reply_markup=reply_markup
    )

async def handle_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.user_data.get("state") != "awaiting_ip" or context.user_data.get("telegram_id") != user_id:
        logger.info(f"Ignored text message '{update.message.text}' from user {user_id} - not in awaiting_ip state or user mismatch")
        return
    ip = update.message.text.strip()
    service_id = context.user_data.get("service_id")
    logger.debug(f"User {user_id} submitted IP {ip} for service {service_id}")
    if not service_id:
        await update.message.reply_text(
            text="⚠️ لطفاً از منوی سرویس‌ها شروع کنید!"
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in handle_ip")
        await update.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, purchase_date, expiry_date, status FROM services WHERE service_id = %s AND telegram_id = %s AND deleted = FALSE",
            (service_id, user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Service {service_id} not found for user {user_id}")
            await update.message.reply_text(
                text="🚫 سرویس مورد نظر یافت نشد!"
            )
            return
        name, purchase_date, expiry_date, status = result
        if is_iranian_ip(ip):
            cursor.execute(
                "UPDATE services SET ip_address = %s WHERE service_id = %s AND telegram_id = %s",
                (ip, service_id, user_id)
            )
            logger.debug(f"IP {ip} registered for service {service_id}, user {user_id}")
            remaining_days = max((expiry_date - datetime.now()).days, 0) if status == "active" else 0
            status_text = "✅" if status == "active" else "⏳"
            purchase_date_str = purchase_date.strftime('%Y-%m-%d')
            expiry_date_str = expiry_date.strftime('%Y-%m-%d')
            keyboard = [
                [InlineKeyboardButton("📍 ثبت آی‌پی جدید", callback_data=f"register_ip_{service_id}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data=f"service_info_{service_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                text=(
                    f"✅ آی‌پی با موفقیت ثبت شد!\n"
                    f"📋 سرویس: {name}\n"
                    f"📅 تاریخ خرید: {purchase_date_str}\n"
                    f"📆 تاریخ انقضا: {expiry_date_str}\n"
                    f"⏰ زمان باقی‌مانده: {remaining_days} روز\n"
                    f"🌐 آی‌پی: {ip}\n"
                    f"وضعیت: {status_text}"
                ),
                reply_markup=reply_markup
            )
        else:
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"service_info_{service_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                text="⚠️ آی‌پی واردشده ایرانی نیست! لطفاً یک آی‌پی معتبر وارد کنید:",
                reply_markup=reply_markup
            )
    except mysql.connector.Error as e:
        logger.error(f"Database error in handle_ip: {e}")
        await update.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()

async def buy_new_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in buy_new_service")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT blocked FROM users WHERE telegram_id = %s", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            logger.warning(f"User {user_id} is blocked")
            await query.message.edit_text(
                text="🚫 شما از خدمات ربات مسدود هستید!"
            )
            return
        cursor.execute("SELECT COUNT(*) FROM pending_payments WHERE telegram_id = %s AND status = 'pending'", (user_id,))
        if cursor.fetchone()[0] > 0:
            await query.message.edit_text(
                text="⚠️ شما یک پرداخت در حال بررسی دارید! لطفاً منتظر تأیید ادمین باشید."
            )
            return
    except mysql.connector.Error as e:
        logger.error(f"Database error in buy_new_service: {e}")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()
    context.user_data["telegram_id"] = user_id
    context.user_data["state"] = "awaiting_service_name"
    logger.debug(f"User {user_id} started buy_new_service")
    keyboard = [
        [InlineKeyboardButton("🎲 انتخاب نام تصادفی", callback_data="random_name")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text="📝 لطفاً نامی برای سرویس خود انتخاب کنید (فقط حروف و اعداد انگلیسی):",
        reply_markup=reply_markup
    )

async def random_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if "telegram_id" not in context.user_data or context.user_data["telegram_id"] != user_id:
        context.user_data["telegram_id"] = user_id
        logger.warning(f"Fixed missing or mismatched telegram_id in random_name for user {user_id}")
    username = query.from_user.username or f"user_{user_id}"
    logger.debug(f"User {user_id} requested random_name")
    name = generate_random_name(user_id, username)
    context.user_data["service_name"] = name
    context.user_data["state"] = "awaiting_duration"
    keyboard = [
        [InlineKeyboardButton("💳 یک‌ماهه | ۷۵,۰۰۰ تومان", callback_data="duration_30")],
        [InlineKeyboardButton("💳 دوماهه | 139,000 تومان", callback_data="duration_60")],
        [InlineKeyboardButton("💳 سه‌ماهه | 195,000 تومان", callback_data="duration_90")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="buy_new_service")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=f"📋 نام سرویس: {name}\nلطفاً دوره سرویس خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    logger.debug(f"Generated random name: {name} for user {user_id}")

async def handle_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.user_data.get("state") != "awaiting_service_name" or context.user_data.get("telegram_id") != user_id:
        logger.info(f"Ignored text message '{update.message.text}' from user {user_id} - not in awaiting_service_name state or user mismatch")
        return
    name = update.message.text.strip()
    logger.debug(f"User {user_id} submitted service name: {name}")
    if not re.match(r'^[a-zA-Z0-9]+$', name):
        keyboard = [
            [InlineKeyboardButton("🎲 انتخاب نام تصادفی", callback_data="random_name")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text="⚠️ لطفاً نامی با حروف و اعداد انگلیسی وارد کنید!",
            reply_markup=reply_markup
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in handle_service_name")
        await update.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM services WHERE telegram_id = %s AND name = %s AND deleted = FALSE",
            (user_id, name)
        )
        if cursor.fetchone()[0] > 0:
            keyboard = [
                [InlineKeyboardButton("🎲 انتخاب نام تصادفی", callback_data="random_name")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                text="⚠️ این نام قبلاً استفاده شده است! لطفاً نام دیگری انتخاب کنید:",
                reply_markup=reply_markup
            )
            return
        context.user_data["service_name"] = name
        context.user_data["state"] = "awaiting_duration"
        keyboard = [
            [InlineKeyboardButton("💳 یک‌ماهه | ۷۵,۰۰۰ تومان", callback_data="duration_30")],
            [InlineKeyboardButton("💳 دوماهه | 139,000 تومان", callback_data="duration_60")],
            [InlineKeyboardButton("💳 سه‌ماهه | 195,000 تومان", callback_data="duration_90")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="buy_new_service")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text="📋 لطفاً دوره سرویس خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
        logger.debug(f"Service name {name} accepted, moving to duration selection for user {user_id}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in handle_service_name: {e}")
        await update.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

async def handle_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    duration = int(query.data.split("_")[1])
    user_id = str(query.from_user.id)
    if "telegram_id" not in context.user_data or context.user_data.get("telegram_id") != user_id:
        context.user_data["telegram_id"] = user_id
        logger.warning(f"Fixed missing or mismatched telegram_id in handle_duration for user {user_id}")
    name = context.user_data.get("service_name")
    if not name:
        logger.error(f"Missing service_name in handle_duration for user {user_id}")
        await query.message.edit_text(
            text="⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    service_id = str(uuid.uuid4())
    price = {"30": 75000, "60": 139000, "90": 195000}[str(duration)]
    context.user_data["service_id"] = service_id
    context.user_data["duration"] = duration
    context.user_data["price"] = price
    context.user_data["state"] = "awaiting_receipt"
    logger.debug(f"User {user_id} selected duration {duration} for service {name}")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="buy_new_service")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=(
            f"💳 برای خرید سرویس {duration} روزه، لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز کنید:\n"
            f"🏦 {CARD_NUMBER}\n"
            f"📄 سپس تصویر رسید پرداخت خود را در پیام بعدی ارسال کنید."
        ),
        reply_markup=reply_markup
    )

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.user_data.get("state") != "awaiting_receipt" or context.user_data.get("telegram_id") != user_id:
        logger.info(f"Ignored message from user {user_id} - not in awaiting_receipt state or user mismatch")
        return
    service_id = context.user_data.get("service_id")
    name = context.user_data.get("service_name")
    duration = context.user_data.get("duration")
    price = context.user_data.get("price")
    if not (service_id and name and duration and price):
        logger.error(f"Missing data in handle_receipt for user {user_id}")
        await update.message.reply_text(
            text="⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    receipt = update.message.photo[-1] if update.message.photo else None
    caption = update.message.caption or "بدون توضیح"
    if not receipt:
        logger.warning(f"User {user_id} sent invalid receipt for service {service_id}")
        await update.message.reply_text(
            text="⚠️ لطفاً تصویر رسید پرداخت را ارسال کنید!"
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in handle_receipt")
        await update.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        payment_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO pending_payments (payment_id, telegram_id, service_id, service_name, duration, price, caption, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (payment_id, user_id, service_id, name, duration, price, caption, "pending")
        )
        logger.debug(f"Payment recorded for user {user_id}, service {service_id}")
        await update.message.reply_text(
            text="⏳ پرداخت شما در حال بررسی است. لطفاً منتظر تأیید ادمین باشید."
        )
        username = update.effective_user.username or f"user_{user_id}"
        # Escape special characters for MarkdownV2
        username_clean = escape_markdown_v2(username)
        name_clean = escape_markdown_v2(name)
        caption_clean = escape_markdown_v2(caption)
        keyboard = [
            [InlineKeyboardButton("✅ پذیرفتن", callback_data=f"approve_payment_{payment_id}_{user_id}")],
            [InlineKeyboardButton("❌ رد کردن", callback_data=f"reject_payment_{payment_id}_{user_id}")],
            [InlineKeyboardButton("🚫 بلاک کردن", callback_data=f"block_user_{payment_id}_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=receipt.file_id,
            caption=(
                f"📬 درخواست پرداخت جدید:\n"
                f"👤 کاربر: [{username_clean}](tg://user?id={user_id})\n"
                f"🆔 آیدی تلگرام: {user_id}\n"
                f"📋 سرویس: {name_clean}\n"
                f"⏰ مدت: {duration} روز\n"
                f"💳 مبلغ: {price:,} تومان\n"
                f"📝 توضیحات: {caption_clean}"
            ),
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        logger.debug(f"Payment notification sent to admin for user {user_id}, service {service_id}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in handle_receipt: {e}")
        await update.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in handle_receipt: {e}")
        await update.message.reply_text(
            text="⚠️ خطای غیرمنتظره‌ای رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if user_id != ADMIN_ID:
        logger.warning(f"User {user_id} attempted unauthorized access to approve_payment")
        await query.message.reply_text(
            text="🚫 دسترسی غیرمجاز!"
        )
        return
    payment_id, target_user_id = query.data.split("_")[2:4]
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in approve_payment")
        await query.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_id, service_name, duration, price FROM pending_payments WHERE payment_id = %s AND telegram_id = %s AND status = 'pending'",
            (payment_id, target_user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Pending payment not found for payment {payment_id}, user {target_user_id}")
            await query.message.reply_text(
                text="🚫 پرداخت مورد نظر یافت نشد!"
            )
            return
        service_id, name, duration, price = result
        purchase_date = datetime.now()
        expiry_date = purchase_date + timedelta(days=duration)
        cursor.execute(
            "INSERT INTO services (service_id, telegram_id, name, purchase_date, expiry_date, duration, status, is_test) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (service_id, target_user_id, name, purchase_date, expiry_date, duration, "active", False)
        )
        cursor.execute(
            "UPDATE pending_payments SET status = 'approved' WHERE payment_id = %s AND telegram_id = %s",
            (payment_id, target_user_id)
        )
        logger.debug(f"Payment approved for payment {payment_id}, user {target_user_id}")
        keyboard = [[InlineKeyboardButton("📋 سرویس‌های من", callback_data="my_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 تبریک! پرداخت شما برای سرویس {name} ({duration} روز) با موفقیت تأیید شد!\n"
                f"📅 تاریخ شروع: {purchase_date.strftime('%Y-%m-%d')}\n"
                f"📆 تاریخ انقضا: {expiry_date.strftime('%Y-%m-%d')}\n"
                f"لطفاً آی‌پی خود را ثبت کنید."
            ),
            reply_markup=reply_markup
        )
        await query.message.reply_text(
            text="✅ پرداخت با موفقیت تأیید شد و سرویس برای کاربر فعال شد."
        )
    except mysql.connector.Error as e:
        logger.error(f"Database error in approve_payment: {e}")
        await query.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if user_id != ADMIN_ID:
        logger.warning(f"User {user_id} attempted unauthorized access to reject_payment")
        await query.message.reply_text(
            text="🚫 دسترسی غیرمجاز!"
        )
        return
    payment_id, target_user_id = query.data.split("_")[2:4]
    context.user_data["action"] = "reject"
    context.user_data["payment_id"] = payment_id
    context.user_data["target_user_id"] = target_user_id
    context.user_data["state"] = "awaiting_reject_reason"
    await query.message.reply_text(
        text="📝 لطفاً دلیل رد پرداخت را وارد کنید:"
    )

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if user_id != ADMIN_ID:
        logger.warning(f"User {user_id} attempted unauthorized access to block_user")
        await query.message.reply_text(
            text="🚫 دسترسی غیرمجاز!"
        )
        return
    payment_id, target_user_id = query.data.split("_")[2:4]
    context.user_data["action"] = "block"
    context.user_data["payment_id"] = payment_id
    context.user_data["target_user_id"] = target_user_id
    context.user_data["state"] = "awaiting_block_reason"
    await query.message.reply_text(
        text="📝 لطفاً دلیل بلاک کردن کاربر را وارد کنید:"
    )

async def handle_admin_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        logger.warning(f"User {user_id} attempted unauthorized access to handle_admin_reason")
        await update.message.reply_text(
            text="🚫 دسترسی غیرمجاز!"
        )
        return
    state = context.user_data.get("state")
    action = context.user_data.get("action")
    payment_id = context.user_data.get("payment_id")
    target_user_id = context.user_data.get("target_user_id")
    reason = update.message.text.strip()
    logger.debug(f"Handling admin reason for user {user_id}: state={state}, action={action}, payment_id={payment_id}, target_user_id={target_user_id}, reason={reason}")
    if not (action and payment_id and target_user_id and reason and state in ["awaiting_reject_reason", "awaiting_block_reason"]):
        logger.error(f"Missing or invalid data in handle_admin_reason for admin {user_id}: action={action}, payment_id={payment_id}, target_user_id={target_user_id}, state={state}")
        await update.message.reply_text(
            text="⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in handle_admin_reason")
        await update.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_name FROM pending_payments WHERE payment_id = %s AND telegram_id = %s AND status = 'pending'",
            (payment_id, target_user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Pending payment not found for payment {payment_id}, user {target_user_id}")
            await update.message.reply_text(
                text="🚫 پرداخت مورد نظر یافت نشد!"
            )
            return
        service_name = result[0]
        if action == "reject":
            cursor.execute(
                "UPDATE pending_payments SET status = 'rejected', reason = %s WHERE payment_id = %s AND telegram_id = %s",
                (reason, payment_id, target_user_id)
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"❌ پرداخت شما برای سرویس {service_name} رد شد.\nدلیل رد شدن: {reason}"
            )
            await update.message.reply_text(
                text=f"✅ پرداخت برای سرویس {service_name} رد شد و دلیل به کاربر ارسال شد."
            )
            logger.debug(f"Payment rejected for payment {payment_id}, user {target_user_id}, reason: {reason}")
        elif action == "block":
            cursor.execute(
                "UPDATE pending_payments SET status = 'rejected', reason = %s WHERE payment_id = %s AND telegram_id = %s",
                (reason, payment_id, target_user_id)
            )
            cursor.execute(
                "UPDATE users SET blocked = TRUE WHERE telegram_id = %s",
                (target_user_id,)
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🚫 شما از خدمات ربات مسدود شدید.\nدلیل مسدود شدن: {reason}"
            )
            await update.message.reply_text(
                text=f"✅ کاربر {target_user_id} بلاک شد و دلیل به او ارسال شد."
            )
            logger.debug(f"User {target_user_id} blocked for payment {payment_id}, reason: {reason}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in handle_admin_reason: {e}")
        await update.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()

async def get_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} requested test service")
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in get_test")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT blocked FROM users WHERE telegram_id = %s", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            logger.warning(f"User {user_id} is blocked")
            await query.message.edit_text(
                text="🚫 شما از خدمات ربات مسدود هستید!"
            )
            return
        cursor.execute(
            "SELECT COUNT(*) FROM services WHERE telegram_id = %s AND is_test = TRUE AND deleted = FALSE",
            (user_id,)
        )
        test_count = cursor.fetchone()[0]
        if test_count > 0:
            keyboard = [[InlineKeyboardButton("🛒 خرید سرویس جدید", callback_data="buy_new_service")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(
                text="🧪 شما پیش‌تر سرویس تست دریافت کرده‌اید! لطفاً برای ادامه، سرویس جدیدی خریداری کنید:",
                reply_markup=reply_markup
            )
            logger.debug(f"User {user_id} already has a test service")
            return
        service_id = str(uuid.uuid4())
        name = f"Test_{user_id}_{str(uuid.uuid4())[:8]}"
        purchase_date = datetime.now()
        expiry_date = purchase_date + timedelta(hours=24)
        cursor.execute(
            "INSERT INTO services (service_id, telegram_id, name, purchase_date, expiry_date, is_test, duration, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (service_id, user_id, name, purchase_date, expiry_date, True, 1, "active")
        )
        cursor.execute(
            "SELECT service_id, telegram_id, name, duration, status, is_test FROM services WHERE service_id = %s AND telegram_id = %s AND deleted = FALSE",
            (service_id, user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.error(f"Failed to verify test service insertion for service_id {service_id}, user {user_id}")
            await query.message.edit_text(
                text="⚠️ خطایی در ثبت سرویس تست رخ داد! لطفاً دوباره تلاش کنید."
            )
            return
        logger.debug(f"Test service inserted and verified: {result}")
        purchase_date_str = purchase_date.strftime('%Y-%m-%d')
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        keyboard = [
            [InlineKeyboardButton("📍 ثبت آی‌پی", callback_data=f"register_ip_{service_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="my_services")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            text=(
                f"🧪 سرویس تست شما با موفقیت فعال شد!\n"
                f"📋 نام سرویس: {name}\n"
                f"📅 تاریخ خرید: {purchase_date_str}\n"
                f"📆 تاریخ انقضا: {expiry_date_str}\n"
                f"⏰ زمان باقی‌مانده: ۱ روز\n"
                f"🌐 آی‌پی: ثبت نشده\n"
                f"وضعیت: ✅"
            ),
            reply_markup=reply_markup
        )
        logger.debug(f"Test service {service_id} created for user {user_id}: name={name}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in get_test: {e}")
        await query.message.edit_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()

async def renew_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split("_")[2]
    user_id = str(query.from_user.id)
    logger.debug(f"User {user_id} requested to renew service {service_id}")
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in renew_service")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM services WHERE service_id = %s AND telegram_id = %s AND deleted = FALSE",
            (service_id, user_id)
        )
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Service {service_id} not found for user {user_id}")
            await query.message.edit_text(
                text="🚫 سرویس مورد نظر یافت نشد!"
            )
            return
        name = result[0]
        context.user_data["service_id"] = service_id
        context.user_data["service_name"] = name
        context.user_data["telegram_id"] = user_id
        context.user_data["state"] = "awaiting_renew_duration"
        keyboard = [
            [InlineKeyboardButton("💳 یک‌ماهه | ۷۵,۰۰۰ تومان", callback_data="renew_duration_30")],
            [InlineKeyboardButton("💳 دوماهه | 139,000 تومان", callback_data="renew_duration_60")],
            [InlineKeyboardButton("💳 سه‌ماهه | 195,000 تومان", callback_data="renew_duration_90")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"service_info_{service_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            text=f"🔄 تمدید سرویس: {name}\nلطفاً دوره تمدید را انتخاب کنید:",
            reply_markup=reply_markup
        )
        logger.debug(f"User {user_id} moved to renew duration for service {service_id}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in renew_service: {e}")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()

async def handle_renew_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    duration = int(query.data.split("_")[2])
    user_id = str(query.from_user.id)
    if "telegram_id" not in context.user_data or context.user_data.get("telegram_id") != user_id:
        context.user_data["telegram_id"] = user_id
        logger.warning(f"Fixed missing or mismatched telegram_id in handle_renew_duration for user {user_id}")
    service_id = context.user_data.get("service_id")
    name = context.user_data.get("service_name")
    if not service_id or not name:
        logger.error(f"Missing service_id or service_name in handle_renew_duration: service_id={service_id}, name={name}")
        await query.message.edit_text(
            text="⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    price = {"30": 75000, "60": 139000, "90": 195000}[str(duration)]
    context.user_data["duration"] = duration
    context.user_data["price"] = price
    context.user_data["state"] = "awaiting_renew_receipt"
    logger.debug(f"User {user_id} selected renew duration {duration} for service {service_id}")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"renew_service_{service_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=(
            f"💳 برای تمدید سرویس {name} ({duration} روزه)، لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز کنید:\n"
            f"🏦 {CARD_NUMBER}\n"
            f"📄 سپس تصویر رسید پرداخت خود را در پیام بعدی ارسال کنید."
        ),
        reply_markup=reply_markup
    )

async def handle_renew_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.user_data.get("state") != "awaiting_renew_receipt" or context.user_data.get("telegram_id") != user_id:
        logger.info(f"Ignored message from user {user_id} - not in awaiting_renew_receipt state or user mismatch")
        return
    service_id = context.user_data.get("service_id")
    name = context.user_data.get("service_name")
    duration = context.user_data.get("duration")
    price = context.user_data.get("price")
    if not (service_id and name and duration and price):
        logger.error(f"Missing data in handle_renew_receipt for user {user_id}")
        await update.message.reply_text(
            text="⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    receipt = update.message.photo[-1] if update.message.photo else None
    caption = update.message.caption or "بدون توضیح"
    if not receipt:
        logger.warning(f"User {user_id} sent invalid receipt for renew service {service_id}")
        await update.message.reply_text(
            text="⚠️ لطفاً تصویر رسید پرداخت را ارسال کنید!"
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in handle_renew_receipt")
        await update.message.reply_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        payment_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO pending_payments (payment_id, telegram_id, service_id, service_name, duration, price, caption, status, is_renewal) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (payment_id, user_id, service_id, name, duration, price, caption, "pending", True)
        )
        logger.debug(f"Renewal payment recorded for user {user_id}, service {service_id}")
        await update.message.reply_text(
            text="⏳ پرداخت شما برای تمدید سرویس در حال بررسی است. لطفاً منتظر تأیید ادمین باشید."
        )
        username = update.effective_user.username or f"user_{user_id}"
        # Escape special characters for MarkdownV2
        username_clean = escape_markdown_v2(username)
        name_clean = escape_markdown_v2(name)
        caption_clean = escape_markdown_v2(caption)
        keyboard = [
            [InlineKeyboardButton("✅ پذیرفتن", callback_data=f"approve_payment_{payment_id}_{user_id}")],
            [InlineKeyboardButton("❌ رد کردن", callback_data=f"reject_payment_{payment_id}_{user_id}")],
            [InlineKeyboardButton("🚫 بلاک کردن", callback_data=f"block_user_{payment_id}_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=receipt.file_id,
            caption=(
                f"📬 درخواست تمدید سرویس جدید:\n"
                f"👤 کاربر: [{username_clean}](tg://user?id={user_id})\n"
                f"🆔 آیدی تلگرام: {user_id}\n"
                f"📋 سرویس: {name_clean}\n"
                f"⏰ مدت: {duration} روز\n"
                f"💳 مبلغ: {price:,} تومان\n"
                f"📝 توضیحات: {caption_clean}"
            ),
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        logger.debug(f"Renewal payment notification sent to admin for user {user_id}, service {service_id}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in handle_renew_receipt: {e}")
        await update.message.reply_text(
            text=f"⚠️ مشکلی در اتصال به سرور رخ داد! خطا: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in handle_renew_receipt: {e}")
        await update.message.reply_text(
            text="⚠️ خطای غیرمنتظره‌ای رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()

async def tutorials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed tutorials")
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="tutorial_android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="tutorial_ios")],
        [InlineKeyboardButton("💻 Windows", callback_data="tutorial_windows")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text="📚 لطفاً پلتفرم مورد نظر خود را برای آموزش تنظیم DNS انتخاب کنید:",
        reply_markup=reply_markup
    )

async def tutorial_android(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed tutorial_android")
    text = (
        f"📱 آموزش تنظیم DNS در اندروید (دو روش):\n\n"
        f"🔧 روش اول: تنظیم دستی DNS روی وای‌فای\n"
        f"1. به تنظیمات دستگاه بروید و گزینه Wi-Fi را انتخاب کنید.\n"
        f"2. روی نام شبکه وای‌فای خود کلیک کنید (یا گزینه Modify Network).\n"
        f"3. گزینه Advanced را انتخاب کنید.\n"
        f"4. تنظیمات IP را از DHCP به Static تغییر دهید.\n"
        f"5. DNSهای قبلی را حذف کرده و مقادیر زیر را وارد کنید:\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}\n"
        f"6. تنظیمات را ذخیره کنید.\n\n"
        f"---\n\n"
        f"📲 روش دوم: استفاده از برنامه DNS Changer\n"
        f"1. برنامه DNS Changer را از گوگل‌پلی دانلود کنید.\n"
        f"2. برنامه را اجرا کرده و DNSهای زیر را وارد کنید:\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}\n"
        f"3. گزینه اتصال را فعال کنید.\n"
        f"4. مجوز VPN را تأیید کنید (صرفاً برای تغییر DNS).\n"
        f"5. اینترنت شما اکنون با DNS جدید فعال است!\n\n"
        f"---\n"
        f"📌 نکات مهم:\n"
        f"- در صورت بروز مشکل، تنظیمات را به DHCP بازگردانید.\n"
        f"- پس از اتمام دوره اشتراک ردکس گیم، تنظیمات را به حالت Automatic برگردانید.\n"
        f"- در صورت تغییر آی‌پی، لطفاً آی‌پی جدید خود را ثبت کنید.\n\n"
        f"✅ تنظیمات تکمیل شد! اکنون اینترنت شما بهینه‌تر است."
    )
    keyboard = [
        [InlineKeyboardButton("📥 دانلود DNS Changer", url="https://play.google.com/store/apps/details?id=com.burakgon.dnschanger")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="tutorials")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=text,
        reply_markup=reply_markup
    )

async def tutorial_ios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed tutorial_ios")
    text = (
        f"🍎 آموزش تنظیم DNS در iOS (دو روش):\n\n"
        f"🔧 روش اول: تنظیم دستی DNS روی وای‌فای\n"
        f"1. به تنظیمات دستگاه بروید و گزینه Wi-Fi را انتخاب کنید.\n"
        f"2. روی آیکون (i) کنار شبکه وای‌فای خود کلیک کنید.\n"
        f"3. به بخش DNS بروید.\n"
        f"4. گزینه Manual را انتخاب کرده و DNSهای قبلی را حذف کنید.\n"
        f"5. DNSهای زیر را اضافه کنید:\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}\n"
        f"6. تنظیمات را ذخیره کنید.\n\n"
        f"---\n\n"
        f"📲 روش دوم: استفاده از برنامه DNS Changer\n"
        f"1. برنامه DNS Changer را از اپ‌استور دانلود کنید.\n"
        f"2. برنامه را اجرا کرده و DNSهای زیر را وارد کنید:\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}\n"
        f"3. گزینه اتصال را فعال کنید.\n"
        f"4. اینترنت شما اکنون با DNS جدید فعال است!\n\n"
        f"---\n"
        f"📌 نکات مهم:\n"
        f"- در صورت بروز مشکل، تنظیمات DNS را به حالت Automatic بازگردانید.\n"
        f"- پس از اتمام دوره اشتراک ردکس گیم، تنظیمات را به حالت Automatic برگردانید.\n"
        f"- در صورت تغییر آی‌پی، لطفاً آی‌پی جدید خود را ثبت کنید.\n\n"
        f"✅ تنظیمات تکمیل شد! اکنون اینترنت شما بهینه‌تر است."
    )
    keyboard = [
        [InlineKeyboardButton("📥 دانلود DNS Changer", url="https://apps.apple.com/us/app/dns-ip-changer-secure-vpn/id1562292463")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="tutorials")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=text,
        reply_markup=reply_markup
    )

async def tutorial_windows(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed tutorial_windows")
    text = (
        f"💻 آموزش تنظیم DNS در ویندوز (دو روش):\n\n"
        f"🔧 روش اول: تنظیم دستی از طریق Control Panel\n"
        f"1. کلیدهای Win+R را فشار دهید، control را تایپ کرده و Enter بزنید.\n"
        f"2. در کنترل پنل:\n"
        f"   - گزینه View by را روی Large icons تنظیم کنید.\n"
        f"   - روی Network and Sharing Center کلیک کنید.\n"
        f"3. در صفحه جدید:\n"
        f"   - از منوی سمت چپ، Change adapter settings را انتخاب کنید.\n"
        f"4. روی اتصال اینترنت خود (Wi-Fi یا Ethernet):\n"
        f"   - راست‌کلیک کرده و Properties را انتخاب کنید.\n"
        f"5. در پنجره Properties:\n"
        f"   - گزینه Internet Protocol Version 4 (TCP/IPv4) را انتخاب کنید.\n"
        f"   - روی Properties کلیک کنید.\n"
        f"6. تنظیم DNS:\n"
        f"   - گزینه Use the following DNS server addresses را فعال کنید.\n"
        f"   - در قسمت Preferred DNS: {IPDNS1}\n"
        f"   - در قسمت Alternate DNS: {IPDNS2}\n"
        f"7. روی OK کلیک کنید.\n"
        f"8. تمام پنجره‌ها را با کلیک روی OK ببندید.\n\n"
        f"---\n\n"
        f"📲 روش دوم: استفاده از DNS Jumper\n"
        f"1. برنامه DNS Jumper را از لینک زیر دانلود کنید.\n"
        f"2. پس از دانلود:\n"
        f"   - فایل ZIP را استخراج کنید.\n"
        f"   - روی DnsJumper.exe دوبار کلیک کنید.\n"
        f"3. در برنامه:\n"
        f"   - از منوی بالا، Network Adapter را انتخاب کنید.\n"
        f"   - در بخش Custom، مقادیر زیر را وارد کنید:\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}\n"
        f"4. روی Apply DNS کلیک کنید.\n"
        f"5. پیام سبز رنگ Successfully applied نشان‌دهنده موفقیت است.\n\n"
        f"---\n"
        f"📌 نکات مهم:\n"
        f"- برای بازگشت به حالت اولیه، در DNS Jumper روی Restore Original DNS کلیک کنید.\n"
        f"- برای تست DNS جدید، در CMD دستور ping 1.1.1.1 را اجرا کنید.\n\n"
        f"✅ تنظیمات تکمیل شد! اکنون اینترنت شما سریع‌تر و امن‌تر است."
    )
    keyboard = [
        [InlineKeyboardButton("📥 دانلود DNS Jumper", url="https://www.sordum.org/files/downloads.php?dns-jumper")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="tutorials")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=text,
        reply_markup=reply_markup
    )

async def tutorials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed tutorials")
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="tutorial_android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="tutorial_ios")],
        [InlineKeyboardButton("💻 Windows", callback_data="tutorial_windows")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text="📚 لطفاً پلتفرم مورد نظر خود را برای آموزش تنظیم DNS انتخاب کنید:",
        reply_markup=reply_markup
    )

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed faq")
    text = (
        f"❓ سوالات متداول:\n\n"
        f"🔍 DNS چیست و آیا خطری برای حساب‌های من دارد؟\n"
        f"خیر، DNS (Domain Name System) مانند دفترچه تلفن اینترنت عمل می‌کند. برای مثال، Google.com را به آی‌پی 8.8.8.8 تبدیل می‌کند و هیچ خطری برای شما یا حساب‌هایتان ندارد.\n\n"
        f"📡 DNS چگونه پینگ را کاهش می‌دهد؟\n"
        f"بدون تنظیم DNS، دستگاه شما به سرورهای DNS عمومی (مانند 1.1.1.1) متصل می‌شود که معمولاً شلوغ و دور هستند. ردکس گیم با سرورهای قدرتمند در ایران و روتینگ بهینه، تأخیر را کاهش داده و پینگ شما را بهبود می‌بخشد.\n\n"
        f"⚠️ آیا استفاده از DNS باعث بن شدن حساب بازی می‌شود؟\n"
        f"خیر، استفاده از DNS ردکس گیم هیچ خطری برای حساب بازی شما ندارد."
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=text,
        reply_markup=reply_markup
    )

async def dns_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.debug(f"User {query.from_user.id} accessed dns_servers")
    text = (
        f"🌐 آدرس‌های DNS ردکس گیم (IPv4):\n"
        f"     - DNS1: {IPDNS1}\n"
        f"     - DNS2: {IPDNS2}"
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        text=text,
        reply_markup=reply_markup
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if user_id != ADMIN_ID:
        logger.warning(f"User {user_id} attempted unauthorized access to stats")
        await query.message.edit_text(
            text="🚫 دسترسی غیرمجاز!"
        )
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database in stats")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM services WHERE is_test = TRUE AND deleted = FALSE")
        test_services = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM services WHERE duration = 30 AND is_test = FALSE")
        one_month = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM services WHERE duration = 60 AND is_test = FALSE")
        two_month = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM services WHERE duration = 90 AND is_test = FALSE")
        three_month = cursor.fetchone()[0]
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            text=(
                f"📊 آمار کاربران:\n"
                f"👥 تعداد کل کاربران: {total_users}\n"
                f"🧪 سرویس‌های تست: {test_services}\n"
                f"💳 سرویس‌های خریداری‌شده:\n"
                f"  • یک‌ماهه: {one_month}\n"
                f"  • دوماهه: {two_month}\n"
                f"  • سه‌ماهه: {three_month}"
            ),
            reply_markup=reply_markup
        )
        logger.debug(f"Stats retrieved for admin {user_id}")
    except mysql.connector.Error as e:
        logger.error(f"Database error in stats: {e}")
        await query.message.edit_text(
            text="⚠️ مشکلی در اتصال به سرور رخ داد! لطفاً دوباره تلاش کنید."
        )
    finally:
        cursor.close()
        conn.close()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    state = context.user_data.get("state")
    logger.debug(f"Handling text message from user {user_id} in state {state}: {update.message.text}")
    if user_id == ADMIN_ID and state in ["awaiting_reject_reason", "awaiting_block_reason"]:
        await handle_admin_reason(update, context)
    elif state == "awaiting_service_name" and context.user_data.get("telegram_id") == user_id:
        await handle_service_name(update, context)
    elif state == "awaiting_ip" and context.user_data.get("telegram_id") == user_id:
        await handle_ip(update, context)
    else:
        logger.info(f"Ignored text message '{update.message.text}' from user {user_id} - invalid state or user mismatch")
        await update.message.reply_text(
            text="⚠️ لطفاً از منوی مناسب اقدام کنید!"
        )

def main():
    lock_fd = acquire_lock()
    try:
        app = Application.builder().token(os.getenv("BOT_TOKEN")).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("menu", menu))
        app.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
        app.add_handler(CallbackQueryHandler(my_services, pattern="my_services"))
        app.add_handler(CallbackQueryHandler(service_info, pattern="service_info_.*"))
        app.add_handler(CallbackQueryHandler(register_ip, pattern="register_ip_.*"))
        app.add_handler(CallbackQueryHandler(manual_ip, pattern="manual_ip_.*"))
        app.add_handler(CallbackQueryHandler(get_test, pattern="get_test"))
        app.add_handler(CallbackQueryHandler(buy_new_service, pattern="buy_new_service"))
        app.add_handler(CallbackQueryHandler(random_name, pattern="random_name"))
        app.add_handler(CallbackQueryHandler(renew_service, pattern="renew_service_.*"))
        app.add_handler(CallbackQueryHandler(handle_renew_duration, pattern="renew_duration_.*"))
        app.add_handler(CallbackQueryHandler(tutorials, pattern="tutorials"))
        app.add_handler(CallbackQueryHandler(tutorial_android, pattern="tutorial_android"))
        app.add_handler(CallbackQueryHandler(tutorial_ios, pattern="tutorial_ios"))
        app.add_handler(CallbackQueryHandler(tutorial_windows, pattern="tutorial_windows"))
        app.add_handler(CallbackQueryHandler(faq, pattern="faq"))
        app.add_handler(CallbackQueryHandler(dns_servers, pattern="dns_servers"))
        app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
        app.add_handler(CallbackQueryHandler(handle_duration, pattern="duration_.*"))
        app.add_handler(CallbackQueryHandler(approve_payment, pattern="approve_payment_.*"))
        app.add_handler(CallbackQueryHandler(reject_payment, pattern="reject_payment_.*"))
        app.add_handler(CallbackQueryHandler(block_user, pattern="block_user_.*"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE, handle_text))
        app.add_handler(MessageHandler(filters.PHOTO & filters.UpdateType.MESSAGE, handle_receipt))
        app.add_handler(MessageHandler(filters.PHOTO & filters.UpdateType.MESSAGE, handle_renew_receipt))
        app.job_queue.run_repeating(check_expired_services, interval=1800, first=0)
        logger.info("Bot started")
        app.run_polling()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

if __name__ == "__main__":
    main()
