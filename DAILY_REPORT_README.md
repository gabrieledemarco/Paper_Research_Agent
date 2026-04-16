# TradingAgents Daily Report System

Automated daily market report generator that analyzes Milan Stock Exchange, European indices, ETFs, and Forex pairs, then sends detailed reports via email and Telegram.

## Features

- **Borsa di Milano (FTSE MIB)**: Automatic analysis of Italian blue-chip stocks
- **European Indices**: DAX, CAC 40, FTSE 100, Euro Stoxx 50
- **Major ETFs**: SPY, QQQ, IWM, VEA, VWO, GLD, TLT
- **Forex**: EUR/USD, GBP/USD, USD/JPY, EUR/GBP, and more
- **Delivery**: Email + Telegram Bot notifications

## Prerequisites

```bash
# Python 3.11+
pip install -r requirements.txt
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

2. Install dependencies:
```bash
pip install -e .
pip install python-telegram-bot schedule aiosmtplib yfinance
```

3. Configure environment:
```bash
cp .env.report .env
```

4. Edit `.env` with your credentials:
```bash
# OpenAI API Key (required for TradingAgents)
OPENAI_API_KEY=your_openai_api_key

# Telegram (get from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Email (Gmail App Password)
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_TO=recipient@example.com
```

## Usage

### Generate report (console only):
```bash
python daily_report.py --no-send
```

### Generate and send:
```bash
python daily_report.py
```

### Save to file:
```bash
python daily_report.py --output report.txt
```

## Cron Setup (Daily 8:00 AM)

```bash
# Edit crontab
crontab -e

# Add this line:
0 8 * * 1-5 cd /path/to/TradingAgents && python daily_report.py >> /var/log/daily_report.log 2>&1
```
*Runs Monday-Friday at 8:00 AM*

## Configuration

Edit these variables in `daily_report.py` to customize:

```python
# Italian Stocks
MILAN_TICKERS = ["ENI.MI", "ENEL.MI", "ISP.MI", ...]

# European Indices
EUROPEAN_INDICES = ["^GDAXI", "^FCHI", "^FTSE", ...]

# ETFs
MAJOR_ETFS = ["SPY", "QQQ", "IWM", "VEA", ...]

# Forex Pairs
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", ...]
```

## Requirements

- OpenAI API Key (for TradingAgents AI analysis)
- Telegram Bot Token (optional)
- SMTP credentials (optional, Gmail App Password)

## License

Apache 2.0 - See [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)