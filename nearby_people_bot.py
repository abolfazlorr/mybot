import os
import math
import random
import sqlite3
import logging

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = "8842347974:AAHi_cTuZ85fjKIuW4AVEYJIwX159Nm1cwY"
DB_PATH = "nearby_users.db"

LOCATION_NOISE = 0.005

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            latitude REAL,
            longitude REAL
        )
        """
    )
    conn.commit()
    conn.close()


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "سلام! 👋 من ربات «افراد نزدیک» هستم.\n\n"
        "🔹 /share — موقعیتت رو به اشتراک بذار تا دیگران بتونن ببیننت\n"
        "🔹 /nearby — افراد نزدیک خودت رو ببین\n"
        "🔹 /stop — خودت رو از لیست حذف کن\n\n"
        "🔒 برای حفظ حریم خصوصی، مکان دقیق هیچ‌کس نشون داده نمی‌شه، "
        "فقط فاصله‌ی تقریبی."
    )
    await update.message.reply_text(text)


async def share_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    button = KeyboardButton("📍 ارسال موقعیت من", request_location=True)
    keyboard = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "برای دیده شدن توسط دیگران، دکمه‌ی زیر رو بزن و موقعیتت رو بفرست:",
        reply_markup=keyboard,
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = update.message.location

    noisy_lat = loc.latitude + random.uniform(-LOCATION_NOISE, LOCATION_NOISE)
    noisy_lon = loc.longitude + random.uniform(-LOCATION_NOISE, LOCATION_NOISE)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO users (user_id, username, first_name, latitude, longitude)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            latitude=excluded.latitude,
            longitude=excluded.longitude
        """,
        (user.id, user.username, user.first_name, noisy_lat, noisy_lon),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ موقعیتت ثبت شد! حالا با /nearby می‌تونی افراد نزدیکت رو ببینی.\n"
        "هر وقت خواستی با /stop از لیست خارج شو.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def nearby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT latitude, longitude FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()

    if row is None:
        await update.message.reply_text(
            "❌ اول باید موقعیتت رو با دستور /share به اشتراک بذاری."
        )
        conn.close()
        return

    my_lat, my_lon = row
    cur = conn.execute(
        "SELECT user_id, username, first_name, latitude, longitude FROM users WHERE user_id != ?",
        (user.id,),
    )
    others = cur.fetchall()
    conn.close()

    if not others:
        await update.message.reply_text("😔 هنوز کس دیگه‌ای موقعیتش رو به اشتراک نگذاشته.")
        return

    distances = []
    for uid, username, first_name, lat, lon in others:
        dist = haversine_km(my_lat, my_lon, lat, lon)
        distances.append((dist, username, first_name))

    distances.sort(key=lambda x: x[0])

    lines = ["📍 افراد نزدیک شما:\n"]
    for dist, username, first_name in distances[:15]:
        name = first_name or "کاربر ناشناس"
        if username:
            contact = f"@{username}"
        else:
            contact = "بدون یوزرنیم (نمی‌توان مستقیم پیام داد)"
        lines.append(f"👤 {name} — تقریباً {dist:.1f} کیلومتر — {contact}")

    await update.message.reply_text("\n".join(lines))


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM users WHERE user_id = ?", (user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ موقعیتت از لیست حذف شد.")


def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("share", share_location))
    app.add_handler(CommandHandler("nearby", nearby))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("ربات در حال اجراست... برای توقف Ctrl+C را بزنید.")
    app.run_polling()


if __name__ == "__main__":
    main()
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ۱. این بخش را موقع نمایش دادن لیست افراد نزدیک (جایی که فاصله را نشان می‌دهی) بگذار:
def show_nearby_users(chat_id, target_user_id, name, distance):
    markup = InlineKeyboardMarkup()
    # target_user_id همان آیدی عددی شخصی است که پیدا شده
    btn = InlineKeyboardButton("✉️ ارسال پیام به این شخص", callback_data=f"msg_{target_user_id}")
    markup.add(btn)
    
    bot.send_message(chat_id, f"👤 {name} - تقریباً {distance} کیلومتر", reply_markup=markup)


# ۲. این بخش را برای مدیریت کلیک روی دکمه و ارسال پیام اضافه کن:
@bot.callback_query_handler(func=lambda call: call.data.startswith('msg_'))
def handle_message_callback(call):
    target_id = call.data.split('_')[1]
    
    # از کاربر می‌خواهیم متن پیامش را بفرستد
    msg = bot.send_message(call.message.chat.id, "لطفاً متن پیام خود را بفرستید تا به صورت ناشناس برای این کاربر ارسال شود:")
    bot.register_next_step_handler(msg, send_to_target, target_id)


def send_to_target(message, target_id):
    text_to_send = f"📩 یک پیام ناشناس جدید:\n\n{message.text}"
    
    try:
        # ارسال پیام به کاربر مقصد
        bot.send_message(target_id, text_to_send)
        bot.reply_to(message, "✅ پیام شما با موفقیت ارسال شد.")
    except Exception as e:
        bot.reply_to(message, "❌ ارسال پیام ناموفق بود (احتمالاً کاربر ربات را استارت نکرده یا بلاک کرده است).")
