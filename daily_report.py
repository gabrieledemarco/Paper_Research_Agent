#!/usr/bin/env python3
"""
Daily Trading Report Generator
Generates automated daily reports for Milan Stock Exchange, European indices, 
ETFs, and Forex pairs, then sends via email and Telegram.

Usage:
    python daily_report.py                    # Run full report and send
    python daily_report.py --tickers "NVDA"    # Analyze specific tickers
    python daily_report.py --no-send         # Generate report without sending
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import yfinance as yf
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

# TradingAgents imports
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - Add your API keys and settings here or use environment
# ============================================================================

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Email Configuration  
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Use App Password for Gmail
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME)
EMAIL_TO = os.getenv("EMAIL_TO", "")

# ============================================================================
# LLM Provider Configuration
# Supported providers: openai, deepseek, google, anthropic, xai, qwen, glm, openrouter
# ============================================================================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")  # Change to your provider

# Model names per provider:
# - openai: gpt-5.4, gpt-4o, etc.
# - deepseek: deepseek-chat, deepseek-coder
# - google: gemini-2.0-flash, gemini-pro
# - anthropic: claude-4-opus-20250214, claude-3-opus
# - xai: grok-4, grok-2
# - qwen: qwen-turbo, qwen-plus
# - glm: glm-4-flash, glm-4
# - openrouter: any model from openrouter

DEEP_THINK_LLM = os.getenv("DEEP_THINK_LLM", "deepseek-chat")
QUICK_THINK_LLM = os.getenv("QUICK_THINK_LLM", "deepseek-chat")

# API Keys - set the one matching your provider:
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")  # Qwen
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")  # GLM
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ============================================================================
# TICKER LISTS
# ============================================================================

# Italian FTSE MIB stocks (Milan Stock Exchange)
MILAN_TICKERS = [
    "ENI.MI",      # Eni
    "ENEL.MI",     # Enel
    "ISP.MI",       # Intesa Sanpaolo
    "UCG.MI",      # UniCredit
    "RACE.MI",     # Ferrari
    "TIT.MI",      # Telecom Italia
    "LDO.MI",      # Leonardo
    "PRY.MI",      # Prysmian
    "MONC.MI",     # Moncler
    "STLA.MI",     # STLA - Stellantis (replaced STM)
]

# European Indices
EUROPEAN_INDICES = [
    "^GDAXI",       # DAX (Germany)
    "^FCHI",        # CAC 40 (France)
    "^FTSE",        # FTSE 100 (UK)
    "^STOXX50E",    # Euro Stoxx 50
    "^KSEMIB",      # FTSE MIB (Italy) - Milano
]

# Major ETFs (US and International)
MAJOR_ETFS = [
    "SPY",          # S&P 500
    "QQQ",          # Nasdaq 100
    "IWM",          # Russell 2000
    "VEA",          # MSCI EAFE
    "VWO",          # MSCI Emerging Markets
    "GLD",          # Gold
    "TLT",          # 20+ Year Treasury
]

# Major Forex Pairs
FOREX_PAIRS = [
    "EURUSD=X",     # EUR/USD
    "GBPUSD=X",     # GBP/USD
    "USDJPY=X",    # USD/JPY
    "EURGBP=X",     # EUR/GBP
    "USDCHF=X",    # USD/CHF
    "AUDUSD=X",    # AUD/USD
    "USDCAD=X",    # USD/CAD
    "NZDUSD=X",    # NZD/USD
]

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def create_agent(config: dict = None) -> TradingAgentsGraph:
    """Create and configure TradingAgents instance with multi-provider support."""
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    # Use configured LLM provider
    config["llm_provider"] = LLM_PROVIDER
    config["deep_think_llm"] = DEEP_THINK_LLM
    config["quick_think_llm"] = QUICK_THINK_LLM
    config["max_debate_rounds"] = 1
    
    # Set correct model names for each provider
    if LLM_PROVIDER == "deepseek":
        config["deep_think_llm"] = "deepseek-chat"
        config["quick_think_llm"] = "deepseek-chat"
    elif LLM_PROVIDER == "google":
        config["deep_think_llm"] = "gemini-2.0-flash"
        config["quick_think_llm"] = "gemini-2.0-flash"
    elif LLM_PROVIDER == "anthropic":
        config["deep_think_llm"] = "claude-sonnet-4-20250514"
        config["quick_think_llm"] = "claude-haiku-3-20240307"
    
    return TradingAgentsGraph(debug=False, config=config)


def analyze_with_agent(ticker: str, date: str = None) -> Optional[dict]:
    """
    Analyze a single ticker using TradingAgents.
    This does deep fundamental, sentiment, news, and technical analysis.
    Note: This is slow - ~1-2 minutes per ticker, so use sparingly.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # Skip weekends
    if datetime.strptime(date, "%Y-%m-%d").weekday() >= 5:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        ta = create_agent()
        _, decision = ta.propagate(ticker, date)
        
        # Parse the decision to extract key insights
        return {
            "ticker": ticker,
            "decision": decision,
            "analysis": str(decision)[:500] if decision else "No decision",
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return None


def get_market_data(tickers: list, period: str = "5d") -> dict:
    """Get market data for multiple tickers."""
    data = {}
    try:
        if tickers:
            tickers_str = " ".join(tickers)
            market = yf.Tickers(tickers_str)
            
            for ticker in tickers:
                try:
                    ticker_obj = market.tickers[ticker]
                    info = ticker_obj.history(period=period)
                    
                    if not info.empty:
                        latest = info.iloc[-1]
                        prev = info.iloc[-2] if len(info) > 1 else latest
                        
                        change = latest['Close'] - prev['Close']
                        change_pct = (change / prev['Close']) * 100 if prev['Close'] > 0 else 0
                        
                        data[ticker] = {
                            "price": round(latest['Close'], 2),
                            "change": round(change, 2),
                            "change_pct": round(change_pct, 2),
                            "volume": int(latest.get('Volume', 0)),
                            "high": round(latest['High'], 2),
                            "low": round(latest['Low'], 2),
                        }
                except Exception as e:
                    logger.warning(f"Error fetching {ticker}: {e}")
                    data[ticker] = {"error": str(e)}
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
    
    return data


def format_market_report(data: dict, title: str) -> str:
    """Format market data into a readable report."""
    report = [f"\n{'='*60}"]
    report.append(f"📊 {title}")
    report.append(f"{'='*60}")
    
    for ticker, info in data.items():
        if "error" in info:
            report.append(f"❌ {ticker}: {info['error']}")
            continue
            
        symbol = "🔴" if info['change'] < 0 else "🟢"
        report.append(
            f"{symbol} {ticker}: €{info['price']} "
            f"({info['change']:+.2f} / {info['change_pct']:+.2f}%)"
        )
        report.append(f"   Range: €{info['low']} - €{info['high']}")
    
    report.append("")
    return "\n".join(report)


def generate_full_report() -> str:
    """Generate the complete daily market report."""
    date = datetime.now().strftime("%Y-%m-%d")
    
    report = []
    report.append("="*70)
    report.append(f"📈 DAILY MARKET REPORT - {date}")
    report.append(f"Generated: {datetime.now().strftime('%H:%M:%S')}")
    report.append("="*70)
    
    # Fetch data for all categories
    logger.info("Fetching Milan stocks data...")
    milan_data = get_market_data(MILAN_TICKERS)
    report.append(format_market_report(milan_data, "BORSA DI MILANO - FTSE MIB"))
    
    logger.info("Fetching European indices data...")
    europe_data = get_market_data(EUROPEAN_INDICES)
    report.append(format_market_report(europe_data, "INDICI EUROPEI"))
    
    logger.info("Fetching ETF data...")
    etf_data = get_market_data(MAJOR_ETFS)
    report.append(format_market_report(etf_data, "PRINCIPALI ETF"))
    
    logger.info("Fetching Forex data...")
    forex_data = get_market_data(FOREX_PAIRS)
    report.append(format_market_report(forex_data, "FOREX - PAIRS PRINCIPALI"))
    
    # Footer
    report.append("\n" + "="*70)
    report.append("📋 Report automatically generated by TradingAgents")
    report.append("="*70)
    
    return "\n".join(report)


# ============================================================================
# NOTIFICATION FUNCTIONS
# ============================================================================

async def send_telegram_message(bot_token: str, chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot."""
    try:
        from telegram import Bot
        
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')
        logger.info("Telegram message sent successfully")
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


async def send_email(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str
) -> bool:
    """Send email via SMTP."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_addr
        
        # Plain text version
        text_part = MIMEText(body, 'plain', 'utf-8')
        
        # HTML version
        html_body = body.replace('\n', '<br>\n')
        html_part = MIMEText(html_body, 'html', 'utf-8')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=username,
            password=password,
            use_tls=True
        )
        
        logger.info(f"Email sent successfully to {to_addr}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False


async def send_notifications(report: str) -> dict:
    """Send report via all configured channels."""
    results = {"telegram": False, "email": False}
    date = datetime.now().strftime("%Y-%m-%d")
    
    # Send via Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        results["telegram"] = await send_telegram_message(
            TELEGRAM_BOT_TOKEN, 
            TELEGRAM_CHAT_ID, 
            f"<pre>{report}</pre>"
        )
    
    # Send via Email
    if SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO:
        results["email"] = await send_email(
            SMTP_HOST,
            SMTP_PORT,
            SMTP_USERNAME,
            SMTP_PASSWORD,
            EMAIL_FROM,
            EMAIL_TO,
            f"📈 Daily Market Report - {date}",
            report
        )
    
    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Daily Trading Report Generator")
    parser.add_argument(
        "--tickers", 
        nargs="+",
        help="Specific tickers to analyze"
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Generate report without sending"
    )
    parser.add_argument(
        "--output",
        help="Save report to file"
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not OPENAI_API_KEY:
        logger.warning(
            "OPENAI_API_KEY not set. Using market data only."
        )
    
    # Generate report
    logger.info("Generating daily market report...")
    report = generate_full_report()
    
    # Print to console
    print(report)
    
    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report)
        logger.info(f"Report saved to {output_path}")
    
    # Send notifications unless --no-send
    if not args.no_send:
        logger.info("Sending notifications...")
        results = asyncio.run(send_notifications(report))
        
        if results["telegram"]:
            print("✅ Report sent via Telegram")
        if results["email"]:
            print("✅ Report sent via Email")
        
        if not any(results.values()):
            print("⚠️ No notifications sent. Check configuration.")
    else:
        print("\nℹ️ Notifications disabled (--no-send)")


if __name__ == "__main__":
    main()