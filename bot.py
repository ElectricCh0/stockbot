import os
import logging
import io
from threading import Thread
from flask import Flask
import yfinance as yf
from google.genai import Client # התיקון כאן
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Flask Server לטובת Render ---
app_flask = Flask('')
@app_flask.route('/')
def home(): return "Bot is Alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

# --- הגדרות לוגים ו-AI ---
logging.basicConfig(level=logging.INFO)
client = Client(api_key=os.environ.get("GEMINI_API_KEY"))

def create_chart(df, ticker):
    """יצירת גרף נרות יפניים בפורמט תמונה"""
    buf = io.BytesIO()
    mpf.plot(df, type='candle', style='charles', title=f"Stock: {ticker}", savefig=buf)
    buf.seek(0)
    return buf

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.upper().strip()
    
    # בדיקה אם המשתמש שלח סימול מניה (מילה אחת באנגלית עד 5 אותיות)
    if user_text.isalpha() and len(user_text) <= 5:
        try:
            status = await update.message.reply_text(f"⏳ מנתח את {user_text}...")
            stock = yf.Ticker(user_text)
            hist = stock.history(period="3mo") # נתונים ל-3 חודשים
            
            if hist.empty:
                await status.edit_text("❌ לא מצאתי נתונים על הסימול הזה. וודא שהוא נכון (למשל AAPL).")
                return

            # יצירת הגרף
            chart = create_chart(hist, user_text)
            
            # יצירת ניתוח טקסטואלי בעזרת Gemini
            prompt = f"נתח בקצרה את מניית {user_text}. מחיר אחרון: {hist['Close'].iloc[-1]:.2f}$. ציין נקודות מעניינות בגרף ב-3 החודשים האחרונים."
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            # שליחת הגרף והניתוח
            await update.message.reply_photo(photo=chart, caption=response.text)
            await status.delete()
            
        except Exception as e:
            logging.error(f"Error: {e}")
            await update.message.reply_text("קרתה שגיאה בניתוח המניה. נסו שוב מאוחר יותר.")
    else:
        # אם זו לא מניה, הבוט פשוט מדבר כצ'אטבוט רגיל
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=user_text + " (ענה בעברית)")
            await update.message.reply_text(response.text)
        except Exception as e:
            logging.error(f"AI Error: {e}")
            await update.message.reply_text("אני מתקשה להבין כרגע, נסו לשאול על מניה ספציפית.")

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("Error: No TELEGRAM_TOKEN found!")
        return
        
    app = Application.builder().token(token).build()
    
    # טיפול בכל הודעת טקסט
    app.add_handler(MessageHandler(filters.TEXT & ~
