import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode
import yfinance as yf
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import json

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_stock_data(ticker: str) -> dict:
    """Fetch comprehensive real-time stock data."""
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info

        # History frames
        hist_1y = stock.history(period="1y")
        hist_6m = stock.history(period="6mo")
        hist_3m = stock.history(period="3mo")
        hist_1m = stock.history(period="1mo")

        # Financials
        try:
            financials     = stock.financials
            balance_sheet  = stock.balance_sheet
            cashflow       = stock.cashflow
        except Exception:
            financials = balance_sheet = cashflow = None

        # Analyst recommendations
        try:
            recommendations = stock.recommendations
            rec_summary     = stock.recommendations_summary
        except Exception:
            recommendations = rec_summary = None

        # Earnings
        try:
            earnings = stock.earnings_dates
        except Exception:
            earnings = None

        return {
            "info":            info,
            "hist_1y":         hist_1y,
            "hist_6m":         hist_6m,
            "hist_3m":         hist_3m,
            "hist_1m":         hist_1m,
            "financials":      financials,
            "balance_sheet":   balance_sheet,
            "cashflow":        cashflow,
            "recommendations": recommendations,
            "rec_summary":     rec_summary,
            "earnings":        earnings,
        }
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None


def safe_val(info: dict, *keys, default="N/A", fmt=None):
    """Safely extract a value from info dict and optionally format it."""
    for k in keys:
        v = info.get(k)
        if v is not None and v != "N/A" and v != 0:
            if fmt:
                try:
                    return fmt(v)
                except Exception:
                    return str(v)
            return v
    return default


def fmt_number(n):
    if n is None or n == "N/A":
        return "N/A"
    try:
        n = float(n)
        if n >= 1e12:
            return f"${n/1e12:.2f}T"
        if n >= 1e9:
            return f"${n/1e9:.2f}B"
        if n >= 1e6:
            return f"${n/1e6:.2f}M"
        return f"${n:,.2f}"
    except Exception:
        return str(n)


def build_analysis_prompt(ticker: str, data: dict) -> str:
    info = data["info"]
    hist = data["hist_1y"]

    current_price  = safe_val(info, "currentPrice", "regularMarketPrice")
    prev_close     = safe_val(info, "previousClose", "regularMarketPreviousClose")
    day_high       = safe_val(info, "dayHigh", "regularMarketDayHigh")
    day_low        = safe_val(info, "dayLow",  "regularMarketDayLow")
    volume         = safe_val(info, "volume",  "regularMarketVolume")
    avg_volume     = safe_val(info, "averageVolume")
    market_cap     = fmt_number(safe_val(info, "marketCap"))
    pe_ratio       = safe_val(info, "trailingPE")
    fwd_pe         = safe_val(info, "forwardPE")
    peg_ratio      = safe_val(info, "pegRatio")
    pb_ratio       = safe_val(info, "priceToBook")
    ps_ratio       = safe_val(info, "priceToSalesTrailing12Months")
    ev_ebitda      = safe_val(info, "enterpriseToEbitda")
    revenue        = fmt_number(safe_val(info, "totalRevenue"))
    revenue_growth = safe_val(info, "revenueGrowth")
    earnings_growth= safe_val(info, "earningsGrowth")
    profit_margin  = safe_val(info, "profitMargins")
    roe            = safe_val(info, "returnOnEquity")
    roa            = safe_val(info, "returnOnAssets")
    debt_equity    = safe_val(info, "debtToEquity")
    current_ratio  = safe_val(info, "currentRatio")
    free_cash_flow = fmt_number(safe_val(info, "freeCashflow"))
    dividend_yield = safe_val(info, "dividendYield")
    beta           = safe_val(info, "beta")
    target_mean    = safe_val(info, "targetMeanPrice")
    target_high    = safe_val(info, "targetHighPrice")
    target_low     = safe_val(info, "targetLowPrice")
    num_analysts   = safe_val(info, "numberOfAnalystOpinions")
    sector         = safe_val(info, "sector")
    industry       = safe_val(info, "industry")
    company_name   = safe_val(info, "longName", "shortName")
    description    = safe_val(info, "longBusinessSummary", default="")[:500]

    # Technical indicators from history
    tech_notes = ""
    if not hist.empty:
        close     = hist["Close"]
        ma50      = close.rolling(50).mean().iloc[-1]  if len(close) >= 50  else None
        ma200     = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        rsi_val   = _calc_rsi(close)
        wk52_high = close.max()
        wk52_low  = close.min()
        ytd_ret   = (close.iloc[-1] / close.iloc[0] - 1) * 100

        tech_notes = f"""
TECHNICAL DATA:
- 52-week High: ${wk52_high:.2f}  |  52-week Low: ${wk52_low:.2f}
- YTD Return: {ytd_ret:.1f}%
- 50-day MA: ${ma50:.2f if ma50 else 'N/A'}
- 200-day MA: ${ma200:.2f if ma200 else 'N/A'}
- RSI (14): {rsi_val:.1f if rsi_val else 'N/A'}
- Price vs 52w High: {((current_price/wk52_high-1)*100):.1f}% below high
"""

    prompt = f"""
You are a professional Wall Street equity analyst. Analyze the following stock and provide a COMPREHENSIVE, DETAILED investment report in Hebrew.

COMPANY: {company_name} ({ticker})
SECTOR: {sector} | INDUSTRY: {industry}
DESCRIPTION: {description}

REAL-TIME PRICE DATA:
- Current Price: ${current_price}
- Previous Close: ${prev_close}
- Day High/Low: ${day_high} / ${day_low}
- Volume: {volume:,} (Avg: {avg_volume:,})

VALUATION METRICS:
- Market Cap: {market_cap}
- P/E (TTM): {pe_ratio}
- Forward P/E: {fwd_pe}
- PEG Ratio: {peg_ratio}
- P/B Ratio: {pb_ratio}
- P/S Ratio: {ps_ratio}
- EV/EBITDA: {ev_ebitda}

FINANCIAL HEALTH:
- Total Revenue: {revenue}
- Revenue Growth: {revenue_growth}
- Earnings Growth: {earnings_growth}
- Profit Margin: {profit_margin}
- ROE: {roe} | ROA: {roa}
- Debt/Equity: {debt_equity}
- Current Ratio: {current_ratio}
- Free Cash Flow: {free_cash_flow}
- Dividend Yield: {dividend_yield}
- Beta: {beta}

ANALYST CONSENSUS:
- Target Price (Mean): ${target_mean}
- Target Range: ${target_low} - ${target_high}
- Number of Analysts: {num_analysts}

{tech_notes}

Please provide a COMPREHENSIVE report in Hebrew with the following sections:

1. **סקירת החברה** - תיאור עסקי מפורט, מודל הכנסות, יתרון תחרותי
2. **ניתוח שווי מקיף** - 
   - הערכת DCF (תזרים מזומנים מהוון) - העריך שווי הוגן
   - השוואת מכפילים לסקטור
   - ניתוח P/E, P/B, EV/EBITDA
   - שווי הוגן מוערך ופוטנציאל עלייה/ירידה
3. **ניתוח פיננסי** - בריאות פיננסית, צמיחה, רווחיות, מינוף
4. **ניתוח טכני** - מגמות, רמות תמיכה/התנגדות, RSI, ממוצעים נעים
5. **קטליסטים וסיכונים** - גורמים שיכולים להניע את המניה למעלה/מטה
6. **קונצנזוס אנליסטים** - מה חושבים האנליסטים, יעד מחיר
7. **תזת השקעה** - ניתוח BULL vs BEAR case
8. **המלצה סופית** - קנה / מכור / החזק עם רמת ביטחון (1-10) ומחיר יעד מוערך שלך

Be specific, use numbers, and provide genuine professional analysis. Include emojis for readability.
"""
    return prompt


def _calc_rsi(prices: pd.Series, period: int = 14) -> float | None:
    try:
        delta  = prices.diff()
        gain   = delta.clip(lower=0).rolling(period).mean()
        loss   = (-delta.clip(upper=0)).rolling(period).mean()
        rs     = gain / loss
        rsi    = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    except Exception:
        return None


# ── Chart generator ───────────────────────────────────────────────────────────

def generate_chart(ticker: str, data: dict, period: str = "1y") -> io.BytesIO:
    hist_map = {
        "1m":  data["hist_1m"],
        "3m":  data["hist_3m"],
        "6m":  data["hist_6m"],
        "1y":  data["hist_1y"],
    }
    hist = hist_map.get(period, data["hist_1y"])

    if hist is None or hist.empty:
        return None

    info         = data["info"]
    company_name = info.get("longName") or info.get("shortName") or ticker
    current_price= info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1]

    fig = plt.figure(figsize=(12, 8), facecolor='#0d1117')
    gs  = fig.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor('#0d1117')
        ax.tick_params(colors='#8b949e', labelsize=8)
        ax.spines['bottom'].set_color('#30363d')
        ax.spines['top'].set_visible(False)
        ax.spines['left'].set_color('#30363d')
        ax.spines['right'].set_visible(False)
        ax.yaxis.label.set_color('#8b949e')
        ax.xaxis.label.set_color('#8b949e')

    close  = hist["Close"]
    volume = hist["Volume"]
    dates  = hist.index

    # Price line + gradient fill
    start_price = close.iloc[0]
    color       = '#3fb950' if close.iloc[-1] >= start_price else '#f85149'

    ax1.plot(dates, close, color=color, linewidth=1.8, zorder=3)

    ax1.fill_between(dates, close, close.min() * 0.99,
                     alpha=0.15, color=color, zorder=2)

    # Moving averages
    if len(close) >= 20:
        ma20 = close.rolling(20).mean()
        ax1.plot(dates, ma20, color='#58a6ff', linewidth=1, linestyle='--',
                 alpha=0.7, label='MA20', zorder=3)
    if len(close) >= 50:
        ma50 = close.rolling(50).mean()
        ax1.plot(dates, ma50, color='#f0883e', linewidth=1, linestyle='--',
                 alpha=0.7, label='MA50', zorder=3)

    ax1.legend(loc='upper left', facecolor='#161b22', edgecolor='#30363d',
               labelcolor='#8b949e', fontsize=8)

    # Price change annotation
    pct_change = (close.iloc[-1] / close.iloc[0] - 1) * 100
    change_str = f"+{pct_change:.1f}%" if pct_change >= 0 else f"{pct_change:.1f}%"
    ax1.set_title(f"{company_name} ({ticker})  |  ${current_price:.2f}  {change_str}",
                  color='#e6edf3', fontsize=13, fontweight='bold', pad=12)
    ax1.set_ylabel('Price (USD)', color='#8b949e', fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}'))

    plt.setp(ax1.get_xticklabels(), visible=False)

    # Volume bars
    vol_colors = ['#3fb950' if c >= o else '#f85149'
                  for c, o in zip(hist["Close"], hist["Open"])]
    ax2.bar(dates, volume, color=vol_colors, alpha=0.7, width=1.5)
    ax2.set_ylabel('Volume', color='#8b949e', fontsize=8)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, _: f'{x/1e6:.0f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
    plt.setp(ax2.get_xticklabels(), visible=False)

    # RSI
    rsi_series = _calc_rsi_series(close)
    if rsi_series is not None:
        ax3.plot(dates, rsi_series, color='#bf91f3', linewidth=1.2)
        ax3.axhline(70, color='#f85149', linestyle='--', alpha=0.5, linewidth=0.8)
        ax3.axhline(30, color='#3fb950', linestyle='--', alpha=0.5, linewidth=0.8)
        ax3.fill_between(dates, rsi_series, 70,
                         where=(rsi_series >= 70), alpha=0.2, color='#f85149')
        ax3.fill_between(dates, rsi_series, 30,
                         where=(rsi_series <= 30), alpha=0.2, color='#3fb950')
        ax3.set_ylim(0, 100)
        ax3.set_ylabel('RSI', color='#8b949e', fontsize=8)
        ax3.yaxis.set_ticks([30, 50, 70])

    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax3.get_xticklabels(), rotation=30, ha='right', fontsize=7)

    plt.suptitle(f"Period: {period.upper()}", color='#6e7681', fontsize=8,
                 y=0.02)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='#0d1117', edgecolor='none')
    buf.seek(0)
    plt.close()
    return buf


def _calc_rsi_series(prices: pd.Series, period: int = 14) -> pd.Series | None:
    try:
        delta = prices.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss
        return 100 - (100 / (1 + rs))
    except Exception:
        return None


# ── Valuation-only prompt ─────────────────────────────────────────────────────

def build_valuation_prompt(ticker: str, data: dict) -> str:
    info = data["info"]
    hist = data["hist_1y"]

    # Gather all financials
    current_price  = safe_val(info, "currentPrice", "regularMarketPrice")
    market_cap     = safe_val(info, "marketCap")
    pe             = safe_val(info, "trailingPE")
    fwd_pe         = safe_val(info, "forwardPE")
    peg            = safe_val(info, "pegRatio")
    pb             = safe_val(info, "priceToBook")
    ps             = safe_val(info, "priceToSalesTrailing12Months")
    ev_ebitda      = safe_val(info, "enterpriseToEbitda")
    ev_revenue     = safe_val(info, "enterpriseToRevenue")
    fcf            = safe_val(info, "freeCashflow")
    revenue        = safe_val(info, "totalRevenue")
    net_income     = safe_val(info, "netIncomeToCommon")
    ebitda         = safe_val(info, "ebitda")
    revenue_growth = safe_val(info, "revenueGrowth")
    earnings_growth= safe_val(info, "earningsGrowth")
    roe            = safe_val(info, "returnOnEquity")
    profit_margin  = safe_val(info, "profitMargins")
    debt_equity    = safe_val(info, "debtToEquity")
    beta           = safe_val(info, "beta")
    shares_out     = safe_val(info, "sharesOutstanding")
    book_value     = safe_val(info, "bookValue")
    company_name   = safe_val(info, "longName", "shortName")
    sector         = safe_val(info, "sector")
    industry       = safe_val(info, "industry")
    target_mean    = safe_val(info, "targetMeanPrice")

    return f"""
You are a top-tier equity valuation specialist (CFA level). Perform a COMPREHENSIVE valuation analysis for {company_name} ({ticker}) in Hebrew.

FINANCIAL DATA:
- Current Price: ${current_price}
- Market Cap: {fmt_number(market_cap)}
- Sector: {sector} | Industry: {industry}

VALUATION MULTIPLES:
- P/E (TTM): {pe} | Forward P/E: {fwd_pe} | PEG: {peg}
- P/B: {pb} | P/S: {ps}
- EV/EBITDA: {ev_ebitda} | EV/Revenue: {ev_revenue}

FINANCIALS:
- Revenue: {fmt_number(revenue)} | Growth: {revenue_growth}
- Net Income: {fmt_number(net_income)} | Earnings Growth: {earnings_growth}
- EBITDA: {fmt_number(ebitda)}
- Free Cash Flow: {fmt_number(fcf)}
- Profit Margin: {profit_margin} | ROE: {roe}
- Debt/Equity: {debt_equity} | Beta: {beta}
- Book Value/Share: ${book_value} | Shares Outstanding: {fmt_number(shares_out)}
- Analyst Target (Mean): ${target_mean}

Provide a DETAILED valuation report in Hebrew with:

1. **הערכת DCF (תזרים מזומנים מהוון)**
   - הנח שיעורי צמיחה לשנים 1-5 ו-6-10
   - WACC מוערך לפי Beta וסטרוקטורת ההון
   - Terminal Value
   - **שווי הוגן מחושב לפי DCF**

2. **הערכה לפי מכפילים**
   - השוואת P/E לממוצע הסקטור ולשוק
   - השוואת EV/EBITDA לענף
   - שווי לפי כל מכפיל

3. **הערכה לפי נכסים (P/B Analysis)**
   - ניתוח שווי הנכסים מול השוק

4. **הערכת Graham Number**
   - חישוב מספר גרהם (√(22.5 × EPS × Book Value))

5. **סיכום הערכות שווי**
   - טבלה עם כל שיטות ההערכה
   - שווי ממוצע משוקלל
   - מרווח ביטחון (Margin of Safety)

6. **מסקנה** - האם המניה זולה / יקרה / במחיר הוגן? עם אחוז פוטנציאל

Use specific numbers in all calculations. Show your work.
"""


# ── Telegram Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *ברוך הבא לבוט ניתוח המניות המקצועי!*\n\n"
        "🔍 פשוט שלח לי *סימול מניה* (ticker) ואנחנו מתחילים!\n\n"
        "📊 *דוגמאות:*\n"
        "`AAPL` - אפל\n"
        "`TSLA` - טסלה\n"
        "`NVDA` - אנבידיה\n"
        "`MSFT` - מיקרוסופט\n\n"
        "⚡ *מה אקבל?*\n"
        "• ניתוח מקיף + תזת השקעה\n"
        "• גרף מחיר עם אינדיקטורים\n"
        "• הערכת שווי מפורטת (DCF, מכפילים)\n"
        "• המלצת קנה/מכור/החזק\n\n"
        "💡 *פקודות:*\n"
        "/chart AAPL - גרף בלבד\n"
        "/value AAPL - הערכת שווי בלבד\n"
        "/help - עזרה"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *מדריך שימוש:*\n\n"
        "*ניתוח מלא:* שלח סימול מניה\n"
        "דוגמה: `AAPL`\n\n"
        "*גרף בלבד:* /chart AAPL\n"
        "*הערכת שווי:* /value AAPL\n\n"
        "🌍 *סימולים נפוצים:*\n"
        "• מניות טכנולוגיה: AAPL, MSFT, GOOGL, META, NVDA, AMZN\n"
        "• רכב/אנרגיה: TSLA, F, GM, XOM\n"
        "• פיננסים: JPM, GS, BAC\n"
        "• ישראל (US): TEVA, NICE, CHKP\n\n"
        "⚠️ *שים לב:* הניתוח הוא לצרכי מידע בלבד, לא המלצה פיננסית."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ שלח סימול מניה. דוגמה: /chart AAPL")
        return
    ticker = context.args[0].upper().strip()
    await send_chart_menu(update, context, ticker)


async def value_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ שלח סימול מניה. דוגמה: /value AAPL")
        return
    ticker = context.args[0].upper().strip()
    await process_valuation(update, context, ticker)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip().upper()
    ticker = ''.join(c for c in text if c.isalnum() or c == '.')

    if not ticker or len(ticker) > 10:
        await update.message.reply_text("❓ שלח סימול מניה תקין, למשל: AAPL")
        return

    # Show main menu
    keyboard = [
        [
            InlineKeyboardButton("📊 ניתוח מלא", callback_data=f"full_{ticker}"),
            InlineKeyboardButton("📈 גרף", callback_data=f"chart_{ticker}"),
        ],
        [
            InlineKeyboardButton("💰 הערכת שווי", callback_data=f"value_{ticker}"),
            InlineKeyboardButton("ℹ️ נתונים בסיסיים", callback_data=f"basic_{ticker}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔍 בחר מה לנתח עבור *{ticker}*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    parts  = data.split("_", 1)
    action = parts[0]
    ticker = parts[1] if len(parts) > 1 else ""

    # Chart period selection
    if action == "chart":
        if ticker in ("1m", "3m", "6m", "1y"):
            # ticker is actually a period here; get real ticker from second part
            period, real_ticker = ticker, context.user_data.get("pending_ticker", "")
            if real_ticker:
                await query.message.reply_text(f"📈 מכין גרף {period} עבור {real_ticker}...")
                stock_data = get_stock_data(real_ticker)
                if not stock_data:
                    await query.message.reply_text("❌ לא הצלחתי לטעון נתונים.")
                    return
                chart_buf = generate_chart(real_ticker, stock_data, period)
                if chart_buf:
                    await query.message.reply_photo(photo=chart_buf,
                        caption=f"📊 {real_ticker} | {period.upper()}")
                return
        # First step - show period menu
        context.user_data["pending_ticker"] = ticker
        keyboard = [
            [
                InlineKeyboardButton("1 חודש",   callback_data="chart_1m"),
                InlineKeyboardButton("3 חודשים", callback_data="chart_3m"),
            ],
            [
                InlineKeyboardButton("6 חודשים", callback_data="chart_6m"),
                InlineKeyboardButton("שנה",      callback_data="chart_1y"),
            ],
        ]
        await query.message.reply_text(
            f"📈 בחר תקופה לגרף של *{ticker}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif action == "full":
        await process_full_analysis(query.message, context, ticker)

    elif action == "value":
        await process_valuation(query.message, context, ticker)

    elif action == "basic":
        await process_basic_data(query.message, context, ticker)


async def process_full_analysis(message, context, ticker: str):
    wait_msg = await message.reply_text(
        f"⏳ מנתח את *{ticker}* - זה ייקח כ-30 שניות...",
        parse_mode=ParseMode.MARKDOWN,
    )

    stock_data = get_stock_data(ticker)
    if not stock_data or not stock_data["info"]:
        await wait_msg.edit_text("❌ לא מצאתי מניה עם הסימול הזה. בדוק שהסימול נכון.")
        return

    # Generate analysis via Gemini
    try:
        prompt   = build_analysis_prompt(ticker, stock_data)
        response = model.generate_content(prompt)
        analysis = response.text
    except Exception as e:
        analysis = f"שגיאה בניתוח AI: {e}"

    # Send chart
    try:
        chart_buf = generate_chart(ticker, stock_data, "1y")
        if chart_buf:
            await message.reply_photo(photo=chart_buf,
                caption=f"📊 {ticker} | גרף שנתי")
    except Exception as e:
        logger.error(f"Chart error: {e}")

    # Send analysis (split if too long)
    await wait_msg.delete()
    max_len = 4000
    for i in range(0, len(analysis), max_len):
        await message.reply_text(analysis[i:i+max_len],
                                  parse_mode=ParseMode.MARKDOWN)


async def process_valuation(message_or_update, context, ticker: str):
    # Support both Update and Message objects
    if hasattr(message_or_update, 'message'):
        message = message_or_update.message
    else:
        message = message_or_update

    wait_msg = await message.reply_text(
        f"💰 מחשב הערכת שווי עבור *{ticker}*...",
        parse_mode=ParseMode.MARKDOWN,
    )

    stock_data = get_stock_data(ticker)
    if not stock_data or not stock_data["info"]:
        await wait_msg.edit_text("❌ לא מצאתי מניה עם הסימול הזה.")
        return

    try:
        prompt   = build_valuation_prompt(ticker, stock_data)
        response = model.generate_content(prompt)
        valuation = response.text
    except Exception as e:
        valuation = f"שגיאה: {e}"

    await wait_msg.delete()
    max_len = 4000
    for i in range(0, len(valuation), max_len):
        await message.reply_text(valuation[i:i+max_len],
                                  parse_mode=ParseMode.MARKDOWN)


async def process_basic_data(message, context, ticker: str):
    wait_msg = await message.reply_text(f"📊 טוען נתונים עבור {ticker}...")

    stock_data = get_stock_data(ticker)
    if not stock_data or not stock_data["info"]:
        await wait_msg.edit_text("❌ לא מצאתי מניה.")
        return

    info = stock_data["info"]
    hist = stock_data["hist_1y"]

    current_price = safe_val(info, "currentPrice", "regularMarketPrice")
    prev_close    = safe_val(info, "previousClose")
    change        = "N/A"
    if current_price != "N/A" and prev_close != "N/A":
        try:
            ch    = float(current_price) - float(prev_close)
            pct   = ch / float(prev_close) * 100
            emoji = "🟢" if ch >= 0 else "🔴"
            change = f"{emoji} {ch:+.2f} ({pct:+.1f}%)"
        except Exception:
            pass

    msg = (
        f"📊 *{info.get('longName', ticker)} ({ticker})*\n"
        f"──────────────────\n"
        f"💵 *מחיר נוכחי:* ${current_price}\n"
        f"📈 *שינוי יומי:* {change}\n"
        f"🏦 *שווי שוק:* {fmt_number(safe_val(info, 'marketCap'))}\n"
        f"──────────────────\n"
        f"📉 *P/E (TTM):* {safe_val(info, 'trailingPE')}\n"
        f"📉 *Forward P/E:* {safe_val(info, 'forwardPE')}\n"
        f"📊 *EV/EBITDA:* {safe_val(info, 'enterpriseToEbitda')}\n"
        f"📖 *P/B:* {safe_val(info, 'priceToBook')}\n"
        f"──────────────────\n"
        f"💰 *רווח/הפסד 12m:* {fmt_number(safe_val(info, 'netIncomeToCommon'))}\n"
        f"💸 *FCF:* {fmt_number(safe_val(info, 'freeCashflow'))}\n"
        f"📦 *הכנסות:* {fmt_number(safe_val(info, 'totalRevenue'))}\n"
        f"──────────────────\n"
        f"🎯 *יעד אנליסטים:* ${safe_val(info, 'targetMeanPrice')}\n"
        f"📡 *ביטא:* {safe_val(info, 'beta')}\n"
        f"🏢 *סקטור:* {safe_val(info, 'sector')}\n"
        f"🏭 *ענף:* {safe_val(info, 'industry')}\n"
    )

    await wait_msg.delete()
    await message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def send_chart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
    context.user_data["pending_ticker"] = ticker
    keyboard = [
        [
            InlineKeyboardButton("1 חודש",   callback_data="chart_1m"),
            InlineKeyboardButton("3 חודשים", callback_data="chart_3m"),
        ],
        [
            InlineKeyboardButton("6 חודשים", callback_data="chart_6m"),
            InlineKeyboardButton("שנה",      callback_data="chart_1y"),
        ],
    ]
    await update.message.reply_text(
        f"📈 בחר תקופה לגרף של *{ticker}*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN is not set!")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("chart",  chart_command))
    app.add_handler(CommandHandler("value",  value_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
