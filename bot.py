import os
from google.genai import Client
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from flask import Flask
import threading

# Flask setup
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask(): app.run(host='0.0.0.0', port=10000)

# בדיקה - האם המפתח קיים במערכת?
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def test_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # הבוט יגיד לנו מה הוא מוצא בתוך Render
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ אני לא מוצא את המפתח! תוודא שב-Render קראת למשתנה GEMINI_API_KEY באותיות גדולות.")
    else:
        # הוא לא יחשוף את כל המפתח, רק יגיד אם הוא קיים
        masked_key = GEMINI_API_KEY[:4] + "..." + GEMINI_API_KEY[-4:]
        await update.message.reply_text(f"✅ מצאתי מפתח! הוא מתחיל ב: {masked_key}. מנסה להתחבר לגוגל...")
        
        try:
            client = Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model="gemini-2.0-flash", contents="Hi")
            await update.message.reply_text("🚀 הצלחתי להתחבר לגוגל! עכשיו שלח לי שם של מניה.")
        except Exception as e:
            await update.message.reply_text(f"❌ המפתח קיים אבל גוגל מחזירה שגיאה: {str(e)}")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, test_bot))
    application.run_polling()
