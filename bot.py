import os
import logging
import io
from threading import Thread
from flask import Flask
import yfinance as yf
import google.generativeai as genai
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- שרת Flask ל-Render ---
app_flask = Flask('')
@app_flask.route('/')
def home(): return "Pro Stock Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

# --- הגדרות ---
logging.basicConfig(level=logging.INFO)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# פונקציה ליצירת גרף נרות יפניים
def create_chart(df, ticker, chart_type='candle'):
    buf = io.BytesIO()
    mpf.plot(df, type=chart_type, style='charles', 
             title=f'\n{ticker} Analysis',
             ylabel='Price ($)',
             volume=True,
             savefig=buf)
    buf.seek(0)
    return buf

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.message.chat_id

    # שלב 1: שימוש ב-Gemini כדי להבין מה המשתמש רוצה
    decision_prompt = f"""
    Analyze this user request: "{user_text}"
    Extract:
    1. Ticker (e.g., AAPL, NVDA or None)
    2. Intent (chart, fundamental, or chat)
    3. Period (1mo, 3mo, 6mo, 1y, 5y - default to 3mo)
    Return ONLY a JSON-like format: Ticker: XXX, Intent: XXX, Period: XXX
    """
    
    try:
        decision_res = model.generate_content(decision_prompt).text
        # חילוץ פשוט של הנתונים מהתשובה
        ticker = None
        for word in decision_res.replace(',', '').split():
            if word.isupper() and len(word) <= 5: ticker = word
        
        period = "3mo"
        if "1y" in user_text: period = "1y"
        elif "6mo" in user_text: period = "6mo"

        # אם זו סתם שיחה
        if not ticker or "chat" in decision_res.lower():
            res = model.generate_content(user_text + " (ענה בעברית ידידותית כעוזר פיננסי חכם)")
            await update.message.reply_text(res.text)
            return

        # שלב 2: ביצוע הפעולה הנדרשת
        status_msg = await update.message.reply_text(f"🚀 מעבד נתונים עבור {ticker}...")
        stock = yf.Ticker(ticker)
        
        if "chart" in decision_res.lower() or "נרות" in user_text:
            df = stock.history(period=period)
            chart_buf = create_chart(df, ticker, 'candle' if "נרות" in user_text else 'line')
            await update.message.reply_photo(photo=chart_buf, caption=f"גרף {ticker} לתקופה של {period}")
        
        if "fundamental" in decision_res.lower() or "ניתוח" in user_text:
            info = stock.info
            analysis_prompt = f"""
            Analyze these stats for {ticker} in Hebrew:
            Price: {info.get('currentPrice')}
            P/E Ratio: {info.get('trailingPE')}
            Market Cap: {info.get('marketCap')}
            Revenue Growth: {info.get('revenueGrowth')}
            Business Summary: {info.get('longBusinessSummary')[:500]}
            Provide a deep professional insight.
            """
            analysis_res = model.generate_content(analysis_prompt)
            await update.message.reply_text(analysis_res.text)
        
        await status_msg.delete()

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("חלה שגיאה בניתוח. וודא שהסימול נכון ושביקשת בצורה ברורה.")

def main():
    app = Application.builder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
