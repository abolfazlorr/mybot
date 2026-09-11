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
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

BOT_TOKEN = "8842347974:AAHi_cTuZ85fjKIuW4AVEYJIwX159Nm1cwY"
DB_PATH = "nearby_users.db"

LOCATION_NOISE = 0.005

# تعریف وضعیت برای ConversationHandler جهت دریافت پیام‌های ناشناس مداوم
WAITING_FOR_MESSAGE = 1

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
        "فقط فاصله‌ی تقریبی و امکان چت ناشناس."
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
        distances.append((uid, dist, first_name))

    distances.sort(key=lambda x: x[1])

    for uid, dist, first_name in distances[:15]:
        name = first_name or "کاربر ناشناس"
        
        # ساخت دکمه شیشه‌ای شروع چت ناشناس
        keyboard = [[InlineKeyboardButton("💬 شروع چت ناشناس", callback_data=f"msg_{uid}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👤 {name} — تقریباً {dist:.1f} کیلومتر",
            reply_markup=reply_markup
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("msg_"):
        target_user_id = query.data.split("_")[1]
        context.user_data["target_user_id"] = target_user_id

        await query.message.reply_text(
            "💬 حالت چت ناشناس برقرار شد!\n"
            "هر پیامی بفرستید برای این کاربر ارسال می‌شود.\n"
            "هر زمان خواستید این گفتگو را تمام کنید، دستور /cancel را بفرستید."
        )
        return WAITING_FOR_MESSAGE


async def receive_anonymous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get("target_user_id")
    text_to_send = update.message.text

    if not target_user_id:
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً دوباره از /nearby شروع کنید.")
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),
            text=f"📩 پیام ناشناس:\n\n{text_to_send}"
        )
        await update.message.reply_text("✅ ارسال شد. پیام بعدی را بفرستید یا /cancel را بزنید.")
    except Exception as e:
        await update.message.reply_text("❌ ارسال پیام ناموفق بود (احتمالاً کاربر ربات را بلاک کرده است).")

    # مکالمه را بسته نگه می‌داریم تا کاربر بتواند پیام‌های بعدی را هم بفرستد
    return WAITING_FOR_MESSAGE


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("target_user_id", None)
    await update.message.reply_text("❌ چت ناشناس به پایان رسید.")
    return ConversationHandler.END


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

    # مدیریت چت ناشناس پیوسته
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^msg_.*")],
        states={
            WAITING_FOR_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_anonymous_message)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("share", share_location))
    app.add_handler(CommandHandler("nearby", nearby))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
