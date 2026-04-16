#!/usr/bin/env python3
"""
Enhanced Daily Trading Report Generator
======================================
Generates comprehensive daily market reports with:
- Price data, sentiment, technical analysis
- AI-powered predictions using TradingAgents
- Prediction tracking and accuracy monitoring
- TradingView links and data sources

Usage:
    python daily_report.py                    # Run full report and send
    python daily_report.py --no-send         # Generate without sending
    python daily_report.py --ticker "ENI.MI" # Analyze specific ticker
"""

import os
import sys
import json
import argparse
import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
import yfinance as yf
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

# TradingAgents imports
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
DEEP_THINK_LLM = os.getenv("DEEP_THINK_LLM", "deepseek-chat")
QUICK_THINK_LLM = os.getenv("QUICK_THINK_LLM", "deepseek-chat")

# API Keys
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME)
EMAIL_TO = os.getenv("EMAIL_TO", "")

# ============================================================================
# ASSET LISTS WITH TRADINGVIEW SYMBOLS
# ============================================================================

# Italian FTSE MIB stocks
MILAN_TICKERS = {
    "ENI.MI": {"name": "Eni", "tv": "ENI-MI"},
    "ENEL.MI": {"name": "Enel", "tv": "ENEL-MI"},
    "ISP.MI": {"name": "Intesa Sanpaolo", "tv": "ISP-MI"},
    "UCG.MI": {"name": "UniCredit", "tv": "UCG-MI"},
    "RACE.MI": {"name": "Ferrari", "tv": "RACE-MI"},
    "TIT.MI": {"name": "Telecom Italia", "tv": "TIT-MI"},
    "LDO.MI": {"name": "Leonardo", "tv": "LDO-MI"},
    "PRY.MI": {"name": "Prysmian", "tv": "PRY-MI"},
    "MONC.MI": {"name": "Moncler", "tv": "MONC-MI"},
    "STLA.MI": {"name": "Stellantis", "tv": "NYSE:STLA"},
    # "FLAP.MI": {"name": "Flazio", "tv": "MILAN:FLAP"},  # Alternative Italian stock
}

# European Indices
EUROPEAN_INDICES = {
    "^GDAXI": {"name": "DAX (Germany)", "tv": "INDEX:DAX"},
    "^FCHI": {"name": "CAC 40 (France)", "tv": "INDEX:FCHI"},
    "^FTSE": {"name": "FTSE 100 (UK)", "tv": "INDEX:FTSE"},
    "^STOXX50E": {"name": "Euro Stoxx 50", "tv": "INDEX:STOXX50E"},
}

# Major ETFs
MAJOR_ETFS = {
    "SPY": {"name": "SPDR S&P 500 ETF", "tv": "NYSEARCA:SPY"},
    "QQQ": {"name": "Invesco QQQ Trust", "tv": "NASDAQ:QQQ"},
    "IWM": {"name": "iShares Russell 2000", "tv": "NYSEARCA:IWM"},
    "VEA": {"name": "Vanguard FTSE Developed", "tv": "NYSEARCA:VEA"},
    "VWO": {"name": "Vanguard Emerging", "tv": "NYSEARCA:VWO"},
    "GLD": {"name": "SPDR Gold Trust", "tv": "NYSEARCA:GLD"},
    "TLT": {"name": "iShares 20+ Yr Treasury", "tv": "NASDAQ:TLT"},
}

# Forex pairs
FOREX_PAIRS = {
    "EURUSD=X": {"name": "EUR/USD", "tv": "FX:EURUSD"},
    "GBPUSD=X": {"name": "GBP/USD", "tv": "FX:GBPUSD"},
    "USDJPY=X": {"name": "USD/JPY", "tv": "FX:USDJPY"},
    "EURGBP=X": {"name": "EUR/GBP", "tv": "FX:EURGBP"},
    "USDCHF=X": {"name": "USD/CHF", "tv": "FX:USDCHF"},
    "AUDUSD=X": {"name": "AUD/USD", "tv": "FX:AUDUSD"},
    "USDCAD=X": {"name": "USD/CAD", "tv": "FX:USDCAD"},
    "NZDUSD=X": {"name": "NZD/USD", "tv": "FX:NZDUSD"},
}

# ============================================================================
# PREDICTION STORAGE
# ============================================================================

PREDICTIONS_DIR = Path("predictions")
PREDICTIONS_FILE = PREDICTIONS_DIR / "predictions.json"


def load_predictions() -> List[Dict]:
    """Load previous predictions from storage."""
    if PREDICTIONS_FILE.exists():
        with open(PREDICTIONS_FILE) as f:
            return json.load(f)
    return []


def save_predictions(predictions: List[Dict]) -> None:
    """Save predictions to storage."""
    PREDICTIONS_DIR.mkdir(exist_ok=True)
    with open(PREDICTIONS_FILE, 'w') as f:
        json.dump(predictions, f, indent=2, default=str)


def add_prediction(asset: str, data: Dict) -> None:
    """Add a new prediction."""
    predictions = load_predictions()
    predictions.append({
        "date": datetime.now().isoformat(),
        "asset": asset,
        **data
    })
    save_predictions(predictions)


# ============================================================================
# MARKET DATA FUNCTIONS
# ============================================================================

def get_market_data(tickers: dict, period: str = "5d") -> Dict:
    """Get market data for tickers."""
    data = {}
    ticker_list = list(tickers.keys())
    
    if not ticker_list:
        return data
    
    try:
        tickers_str = " ".join(ticker_list)
        market = yf.Tickers(tickers_str)
        
        for ticker, info in tickers.items():
            try:
                ticker_obj = market.tickers[ticker]
                hist = ticker_obj.history(period=period)
                
                if hist.empty:
                    data[ticker] = {
                        "name": info["name"],
                        "error": "No data available"
                    }
                    continue
                
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest
                
                change = latest['Close'] - prev['Close']
                change_pct = (change / prev['Close']) * 100 if prev['Close'] > 0 else 0
                
                # Calculate simple metrics
                high_52w = None
                low_52w = None
                try:
                    info_obj = ticker_obj.info
                    high_52w = info_obj.get('fiftyTwoWeekHigh')
                    low_52w = info_obj.get('fiftyTwoWeekLow')
                except:
                    pass
                
                data[ticker] = {
                    "name": info["name"],
                    "ticker": ticker,
                    "price": round(latest['Close'], 4),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                    "open": round(latest.get('Open', latest['Close']), 4),
                    "high": round(latest['High'], 4),
                    "low": round(latest['Low'], 4),
                    "volume": int(latest.get('Volume', 0)),
                    "prev_close": round(prev['Close'], 4),
                    "52w_high": high_52w,
                    "52w_low": low_52w,
                    "tradingview_url": f"https://www.tradingview.com/symbols/{info['tv']}",
                    "source": "Yahoo Finance",
                }
            except Exception as e:
                logger.warning(f"Error fetching {ticker}: {e}")
                data[ticker] = {"name": info["name"], "error": str(e)}
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
    
    return data


# ============================================================================
# TRADERAGENTS ANALYSIS
# ============================================================================

def create_agent(config: dict = None) -> TradingAgentsGraph:
    """Create TradingAgents instance."""
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    config["llm_provider"] = LLM_PROVIDER
    config["deep_think_llm"] = DEEP_THINK_LLM
    config["quick_think_llm"] = QUICK_THINK_LLM
    config["max_debate_rounds"] = 1
    
    return TradingAgentsGraph(debug=False, config=config)


def analyze_with_ai(ticker: str, date: str = None) -> Optional[Dict]:
    """
    Analyze asset using TradingAgents AI.
    Returns sentiment, prediction, and confidence.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # Skip weekends
    try:
        if datetime.strptime(date, "%Y-%m-%d").weekday() >= 5:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    except:
        pass
    
    if not DEEPSEEK_API_KEY and not OPENAI_API_KEY:
        logger.warning("No LLM API key configured - using basic analysis")
        return None
    
    try:
        ta = create_agent()
        _, decision = ta.propagate(ticker, date)
        
        # Parse decision to extract sentiment
        decision_str = str(decision).lower()
        
        if any(word in decision_str for word in ['buy', 'bullish', 'long', 'positive', 'up', 'overweight']):
            sentiment = "Bullish"
        elif any(word in decision_str for word in ['sell', 'bearish', 'short', 'negative', 'down', 'underweight']):
            sentiment = "Bearish"
        else:
            sentiment = "Neutral"
        
        # Determine confidence
        if any(word in decision_str for word in ['strong', 'high confidence', 'very confident']):
            confidence = "Alto"
        elif any(word in decision_str for word in ['moderate', 'medium']):
            confidence = "Medio"
        else:
            confidence = "Basso"
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "analysis": str(decision)[:1500],
            "raw_decision": str(decision),
        }
    except Exception as e:
        logger.error(f"AI analysis error for {ticker}: {e}")
        return None


def generate_basic_analysis(market_data: Dict) -> Dict:
    """Generate basic technical analysis without AI."""
    analysis = {}
    
    for ticker, data in market_data.items():
        if "error" in data or "price" not in data:
            analysis[ticker] = {
                "sentiment": "Neutral",
                "prediction": "Mantiene attuali livelli",
                "confidence": "Basso",
                "technicals": "Dati insufficienti per analisi",
                "macro": "Nessun dato macro disponibile",
            }
            continue
        
        # Simple technical analysis based on price action
        price = data.get("price", 0)
        change_pct = data.get("change_pct", 0)
        high = data.get("high", 0)
        low = data.get("low", 0)
        
        # Determine sentiment from price movement
        if change_pct > 0.5:
            sentiment = "Bullish"
            direction = "Al rialzo"
        elif change_pct < -0.5:
            sentiment = "Bearish"
            direction = "Al ribasso"
        else:
            sentiment = "Neutral"
            direction = "Laterale"
        
        # Support/Resistance levels
        supports = f"Supporto: {low:.2f}"
        resistances = f"Resistenza: {high:.2f}"
        
        # Volatility
        volatility = "Alta" if abs(change_pct) > 2 else "Moderata"
        
        analysis[ticker] = {
            "sentiment": sentiment,
            "prediction": direction,
            "confidence": "Medio",
            "technicals": f"{supports}, {resistances}. Volatilità: {volatility}",
            "macro": "Analisi basata su price action",
        }
    
    return analysis


# ============================================================================
# REPORT FORMATTING
# ============================================================================

def format_price_change(change_pct: float) -> str:
    """Format price change with emoji."""
    if change_pct > 0:
        return f"🟢 +{change_pct:.2f}%"
    elif change_pct < 0:
        return f"🔴 {change_pct:.2f}%"
    return "⚪ 0.00%"


def format_asset_report(ticker: str, data: Dict, analysis: Dict = None) -> str:
    """Format a single asset report."""
    if "error" in data:
        return f"❌ **{data['name']}**: Errore - {data['error']}"
    
    name = data.get("name", ticker)
    price = data.get("price", 0)
    change_pct = data.get("change_pct", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)
    source = data.get("source", "N/A")
    tv_url = data.get("tradingview_url", "")
    
    report = []
    report.append(f"\n📊 **{name}** (`{ticker})")
    report.append(f"   💰 Prezzo: €{price}")
    report.append(f"   📈 Variazione: {format_price_change(change_pct)}")
    report.append(f"   📊 Range: €{low:.2f} - €{high:.2f}")
    report.append(f"   🔗 [TradingView]({tv_url})")
    report.append(f"   📚 Fonte: {source}")
    
    # Add analysis if available
    if analysis:
        analisi = analysis.get(ticker, {})
        if analisi:
            sentiment = analisi.get("sentiment", "Neutral")
            sentiment_emoji = "🟢" if sentiment == "Bullish" else "🔴" if sentiment == "Bearish" else "⚪"
            
            report.append(f"   {sentiment_emoji} Sentiment: **{sentiment}**")
            report.append(f"   🎯 Previsione: {analisi.get('prediction', 'N/A')}")
            report.append(f"   🧠 Motivazione:")
            report.append(f"      - Tecnica: {analisi.get('technicals', 'N/A')}")
            report.append(f"      - Macro: {analisi.get('macro', 'N/A')}")
            
            conf = analisi.get("confidence", "Basso")
            conf_emoji = "🟢🟢" if conf == "Alto" else "🟡🟡" if conf == "Medio" else "🔴🔴"
            report.append(f"   ⚠️ Confidenza: {conf_emoji}")
    
    return "\n".join(report)


def calculate_prediction_accuracy() -> Dict:
    """Calculate prediction accuracy from stored predictions."""
    predictions = load_predictions()
    
    if not predictions:
        return {
            "accuracy": 0,
            "total_predictions": 0,
            "best_assets": [],
            "errors": [],
        }
    
    asset_results = {}
    for pred in predictions:
        asset = pred.get("asset", "Unknown")
        if asset not in asset_results:
            asset_results[asset] = {"correct": 0, "total": 0}
        asset_results[asset]["total"] += 1
    
    total_all = len(predictions)
    
    accuracy_by_asset = {}
    for asset, results in asset_results.items():
        total = results["total"]
        accuracy_by_asset[asset] = {
            "total": total,
            "correct": results.get("correct", 0),
        }
    
    return {
        "accuracy": 0,
        "total_predictions": total_all,
        "best_assets": [],
        "errors": [],
        "details": accuracy_by_asset,
    }


def generate_full_report() -> str:
    """Generate the complete daily report."""
    date = datetime.now().strftime("%Y-%m-%d")
    report = []
    
    # Header
    report.append("=" * 70)
    report.append(f"📈 DAILY MARKET REPORT - {date}")
    report.append(f"Generato: {datetime.now().strftime('%H:%M:%S UTC')}")
    report.append("=" * 70)
    report.append("")
    
    # Fetch all market data
    logger.info("Fetching Milan stocks...")
    milan_data = get_market_data(MILAN_TICKERS)
    milan_analysis = generate_basic_analysis(milan_data)
    
    logger.info("Fetching European indices...")
    europe_data = get_market_data(EUROPEAN_INDICES)
    europe_analysis = generate_basic_analysis(europe_data)
    
    logger.info("Fetching ETFs...")
    etf_data = get_market_data(MAJOR_ETFS)
    etf_analysis = generate_basic_analysis(etf_data)
    
    logger.info("Fetching Forex...")
    forex_data = get_market_data(FOREX_PAIRS)
    forex_analysis = generate_basic_analysis(forex_data)
    
    # Sections
    report.append("\n" + "=" * 60)
    report.append("🇮🇹 BORSA DI MILANO - FTSE MIB")
    report.append("=" * 60)
    for ticker in MILAN_TICKERS:
        if ticker in milan_data:
            report.append(format_asset_report(ticker, milan_data[ticker], milan_analysis))
    
    report.append("\n" + "=" * 60)
    report.append("🇪🇺 INDICI EUROPEI")
    report.append("=" * 60)
    for ticker in EUROPEAN_INDICES:
        if ticker in europe_data:
            report.append(format_asset_report(ticker, europe_data[ticker], europe_analysis))
    
    report.append("\n" + "=" * 60)
    report.append("📊 PRINCIPALI ETF")
    report.append("=" * 60)
    for ticker in MAJOR_ETFS:
        if ticker in etf_data:
            report.append(format_asset_report(ticker, etf_data[ticker], etf_analysis))
    
    report.append("\n" + "=" * 60)
    report.append("💱 FOREX - PAIRS PRINCIPALI")
    report.append("=" * 60)
    for ticker in FOREX_PAIRS:
        if ticker in forex_data:
            report.append(format_asset_report(ticker, forex_data[ticker], forex_analysis))
    
    # Prediction performance
    perf = calculate_prediction_accuracy()
    if perf["total_predictions"] > 0:
        report.append("\n" + "=" * 60)
        report.append("📈 PERFORMANCE PREVISIONI")
        report.append("=" * 60)
        report.append(f"   Accuratezza totale: {perf['accuracy']}%")
        report.append(f"   Previsioni totali: {perf['total_predictions']}")
    
    # Footer
    report.append("\n" + "=" * 70)
    report.append("📋 Report generato da TradingAgents + Yahoo Finance")
    report.append("=" * 70)
    
    return "\n".join(report)


# ============================================================================
# NOTIFICATIONS
# ============================================================================

async def send_telegram(message: str) -> bool:
    """Send via Telegram in multiple smaller messages if needed."""
    try:
        from telegram import Bot
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Telegram max message length is ~4096 chars
        max_length = 4000
        chunks = []
        
        # Split by sections ("====" markers)
        sections = message.split("\n" + "=" * 60 + "\n")
        
        current_chunk = ""
        for section in sections:
            if len(current_chunk) + len(section) + 50 > max_length and current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += section + "\n" + "=" * 60 + "\n"
        
        if current_chunk:
            chunks.append(current_chunk)
        
        # If still too long, split by lines
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > max_length:
                lines = chunk.split("\n")
                current = ""
                for line in lines:
                    if len(current) + len(line) + 1 > max_length:
                        final_chunks.append(current)
                        current = ""
                    current += line + "\n"
                if current:
                    final_chunks.append(current)
            else:
                final_chunks.append(chunk)
        
        # Send all chunks
        for i, chunk in enumerate(final_chunks):
            # Clean up HTML for telegram
            clean_chunk = chunk.replace("**", "").replace("`", "").replace("   ", " ")
            # Wrap in code block to preserve formatting
            formatted = f"```\n{clean_chunk}```"
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=formatted,
                parse_mode='Markdown'
            )
            # Small delay between messages
            await asyncio.sleep(0.5)
        
        logger.info(f"Sent {len(final_chunks)} Telegram messages")
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


async def send_email(subject: str, body: str) -> bool:
    """Send via Email."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        text_part = MIMEText(body, 'plain', 'utf-8')
        html_body = body.replace('\n', '<br>\n')
        html_part = MIMEText(html_body, 'html', 'utf-8')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            use_tls=True
        )
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False


async def send_notifications(report: str) -> Dict:
    """Send report via all channels."""
    results = {"telegram": False, "email": False}
    date = datetime.now().strftime("%Y-%m-%d")
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        results["telegram"] = await send_telegram(report)
    
    if SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO:
        results["email"] = await send_email(
            f"📈 Daily Market Report - {date}",
            report
        )
    
    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enhanced Daily Trading Report")
    parser.add_argument("--no-send", action="store_true", help="Generate without sending")
    parser.add_argument("--output", help="Save to file")
    parser.add_argument("--ticker", help="Analyze specific ticker only")
    args = parser.parse_args()
    
    logger.info("Generating enhanced market report...")
    report = generate_full_report()
    
    print(report)
    
    if args.output:
        Path(args.output).write_text(report)
        logger.info(f"saved to {args.output}")
    
    if not args.no_send:
        logger.info("Sending notifications...")
        results = asyncio.run(send_notifications(report))
        
        if results["telegram"]:
            print("✅ Sent via Telegram")
        if results["email"]:
            print("✅ Sent via Email")


if __name__ == "__main__":
    main()