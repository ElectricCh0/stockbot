import os
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# שרת בסיסי ל-Render
app = Flask('')
@app.route('/')
def home(): return "OK"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# הפעלת השרת ב-Thread נפרד
Thread(target=run, daemon=True).start()

# הגדרות בוט פשוטות
logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("הבוט עובד!")

def main():
    if not TOKEN:
        print("No Token found!")
        return
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    print("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
