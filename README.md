# 📊 בוט ניתוח מניות - Stock Analysis Bot

בוט טלגרם מקצועי לניתוח מניות בזמן אמת עם AI.

## 🚀 העלאה ל-Render (חינמי)

### שלב 1 - GitHub
1. כנס ל-github.com וצור חשבון חינמי
2. לחץ "New repository"
3. שם: `stock-bot`
4. לחץ "Create repository"
5. העלה את 3 הקבצים: `bot.py`, `requirements.txt`, `render.yaml`

### שלב 2 - Render
1. כנס ל-render.com
2. התחבר עם חשבון GitHub
3. לחץ "New" → "Blueprint"
4. בחר את הריפו `stock-bot`
5. Render יזהה את render.yaml אוטומטית

### שלב 3 - משתני סביבה
בהגדרות השירות ב-Render:
- `TELEGRAM_TOKEN` = הטוקן מ-BotFather
- `GEMINI_API_KEY` = המפתח מ-Google AI Studio

### שלב 4 - הפעלה
לחץ "Deploy" - הבוט יעלה תוך 2-3 דקות!

## 📱 שימוש
- שלח סימול מניה: `AAPL`, `TSLA`, `NVDA`
- /chart AAPL - גרף
- /value AAPL - הערכת שווי
- /help - עזרה
