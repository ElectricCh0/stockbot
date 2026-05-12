import os
import logging
import asyncio
from threading import Thread
from flask import Flask
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

# ── Flask Server for Keep-Alive ──────────────────────────────────────────────
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "I am alive!"

def run_flask():
    # Render משתמש בפורט 8080 כברירת מחדל לשירותי Web
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

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
