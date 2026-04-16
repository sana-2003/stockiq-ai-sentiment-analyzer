"""
StockIQ — Real-Time Stock Sentiment Analyzer
Reddit + News → Groq AI sentiment → WebSocket live dashboard
"""

import asyncio
import json
import os
import uuid
import random
from datetime import datetime, timedelta
from typing import Optional
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ── Groq ──────────────────────────────────────────────────────────────────────
try:
    from groq import Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    GROQ_AVAILABLE = bool(GROQ_API_KEY)
except Exception:
    GROQ_AVAILABLE = False
    groq_client = None

# ── Optional real data sources ────────────────────────────────────────────────
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import praw
    REDDIT_AVAILABLE = True
except ImportError:
    REDDIT_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="StockIQ API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── In-memory store ───────────────────────────────────────────────────────────
# Each ticker stores last 50 sentiment data points
ticker_data: dict[str, deque] = {}
ticker_scores: dict[str, float] = {}
connected_clients: list[WebSocket] = []
is_running = False

TRACKED_TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "AMD"]

# ── Demo news headlines ───────────────────────────────────────────────────────
DEMO_HEADLINES = {
    "AAPL": [
        ("Apple hits record iPhone sales in Q4, analysts raise price targets", "positive"),
        ("Apple faces antitrust scrutiny in EU over App Store policies", "negative"),
        ("Apple Vision Pro shipping delays frustrate early adopters", "negative"),
        ("Apple launches new AI features in iOS update, stock jumps", "positive"),
        ("Warren Buffett increases Apple stake, bullish signal for investors", "positive"),
        ("Apple supply chain disruptions in Asia raise concerns", "negative"),
        ("Apple reports strong services revenue growth, beats estimates", "positive"),
        ("Apple share buyback program extended by $90 billion", "positive"),
    ],
    "TSLA": [
        ("Tesla Cybertruck deliveries exceed expectations in first quarter", "positive"),
        ("Tesla cuts prices again amid rising EV competition from BYD", "negative"),
        ("Elon Musk announces new Tesla factory in India", "positive"),
        ("Tesla missing delivery targets raises investor concerns", "negative"),
        ("Tesla FSD beta receives positive reviews from early testers", "positive"),
        ("Tesla faces recall over software issue in Model S", "negative"),
        ("Tesla energy storage business growing faster than vehicles", "positive"),
        ("Musk sells more Tesla shares for Twitter acquisition costs", "negative"),
    ],
    "NVDA": [
        ("Nvidia reports blowout earnings, data center revenue triples", "positive"),
        ("Nvidia H100 demand outstrips supply by massive margin", "positive"),
        ("Nvidia faces export restrictions to China, shares slide", "negative"),
        ("Nvidia announces next-gen Blackwell GPU architecture", "positive"),
        ("Nvidia stock hits all-time high on AI spending boom", "positive"),
        ("Competition from AMD and Intel may pressure Nvidia margins", "negative"),
        ("Microsoft and Google order billions in Nvidia chips", "positive"),
        ("Nvidia CEO Jensen Huang sees no slowdown in AI demand", "positive"),
    ],
    "MSFT": [
        ("Microsoft Copilot adoption accelerating across enterprise clients", "positive"),
        ("Microsoft Azure revenue surges 30% on AI infrastructure demand", "positive"),
        ("Microsoft faces regulatory hurdles in Activision integration", "negative"),
        ("Microsoft Teams usage reaches new record amid remote work trend", "positive"),
        ("Microsoft invests additional $10B in OpenAI partnership", "positive"),
        ("Microsoft security breach raises concerns about cloud safety", "negative"),
        ("Microsoft gaming division shows strong Game Pass growth", "positive"),
        ("Microsoft beats earnings estimates, raises full year guidance", "positive"),
    ],
    "GOOGL": [
        ("Google Gemini Ultra outperforms GPT-4 on key benchmarks", "positive"),
        ("Google faces $5B antitrust fine from EU regulators", "negative"),
        ("Google Cloud revenue accelerates on AI workload demand", "positive"),
        ("Google layoffs affect 12000 employees across divisions", "negative"),
        ("Google Search maintains dominant market share despite AI competition", "positive"),
        ("Google YouTube ad revenue rebounds strongly in Q3", "positive"),
        ("Alphabet announces $70B buyback program, investors cheer", "positive"),
        ("Google accused of anticompetitive practices in ad market", "negative"),
    ],
    "AMZN": [
        ("Amazon AWS revenue growth reaccelerates to 17% in Q4", "positive"),
        ("Amazon Prime membership hits 200 million globally", "positive"),
        ("Amazon faces union organizing effort at major warehouse", "negative"),
        ("Amazon advertising business now rivals Google and Meta", "positive"),
        ("Amazon cost-cutting program saves $10B annually", "positive"),
        ("Amazon pharmacy business disrupting traditional drugstores", "positive"),
        ("Amazon faces criticism over working conditions report", "negative"),
        ("Amazon Bedrock AI platform gaining enterprise traction", "positive"),
    ],
    "META": [
        ("Meta AI assistant reaches 400M monthly active users", "positive"),
        ("Meta Quest 3 sales beat expectations holiday quarter", "positive"),
        ("Meta faces teen safety lawsuit from 40 state attorneys general", "negative"),
        ("Meta Threads gains 100M users in record time", "positive"),
        ("Meta advertising revenue hits all-time high in Q4", "positive"),
        ("Meta Reality Labs losses exceed $15B in fiscal year", "negative"),
        ("Zuckerberg announces major AI infrastructure investment", "positive"),
        ("Meta faces data privacy investigation in Ireland", "negative"),
    ],
    "AMD": [
        ("AMD MI300 AI chip sees massive orders from hyperscalers", "positive"),
        ("AMD gains GPU market share from Nvidia in data centers", "positive"),
        ("AMD Ryzen processors outselling Intel in laptop segment", "positive"),
        ("AMD faces supply constraints on latest AI accelerators", "negative"),
        ("AMD CEO Lisa Su raises AI chip revenue guidance sharply", "positive"),
        ("AMD acquires AI startup to strengthen software stack", "positive"),
        ("AMD gaming GPU division reports flat revenue quarter", "negative"),
        ("AMD partners with Microsoft for custom AI silicon", "positive"),
    ],
}

REDDIT_POSTS = {
    "AAPL": [
        ("AAPL to the moon 🚀 services revenue is insane", "positive"),
        ("Sold my AAPL calls, feels overvalued at current PE", "negative"),
        ("Apple ecosystem lock-in is unbeatable long term hold", "positive"),
        ("Cook needs to show us the next big thing, vision pro flopped", "negative"),
        ("Just bought more AAPL on the dip, never going wrong buying apple", "positive"),
    ],
    "TSLA": [
        ("TSLA puts printing money rn, competition is eating them alive", "negative"),
        ("Full self driving is finally working, Tesla is going to 1000", "positive"),
        ("Musk is distracted with Twitter/X, TSLA suffering", "negative"),
        ("Energy business alone is worth the current market cap", "positive"),
        ("TSLA bears about to get destroyed next earnings", "positive"),
    ],
    "NVDA": [
        ("NVDA is the picks and shovels play of the AI gold rush", "positive"),
        ("Nvidia at 40x revenue is insane valuation, bubble territory", "negative"),
        ("Every major tech company is buying as many H100s as possible", "positive"),
        ("AMD closing the gap faster than people realize", "negative"),
        ("Sold covered calls on NVDA, this thing prints", "positive"),
    ],
    "MSFT": [
        ("MSFT is the safest AI play IMO, copilot is everywhere", "positive"),
        ("Azure growth reaccelerating is massive, buy the dip", "positive"),
        ("MSFT is boring but reliable, my biggest holding", "positive"),
        ("Teams is terrible but enterprises keep buying it anyway", "negative"),
        ("OpenAI partnership is the best acquisition in tech history", "positive"),
    ],
    "GOOGL": [
        ("Google is losing the AI race to Microsoft and OpenAI", "negative"),
        ("GOOGL at these prices is insane value, search is a moat", "positive"),
        ("Antitrust risk is real and underpriced in GOOGL", "negative"),
        ("Cloud business is finally showing real acceleration", "positive"),
        ("Gemini is actually good now, Google is back in the AI race", "positive"),
    ],
    "AMZN": [
        ("AWS is the backbone of the internet, AMZN is a steal", "positive"),
        ("Amazon logistics costs still too high, margins under pressure", "negative"),
        ("Prime video winning Emmy awards, underrated asset", "positive"),
        ("AMZN advertising is the most underrated business in tech", "positive"),
        ("Jassy is a better CEO than Bezos was honestly", "positive"),
    ],
    "META": [
        ("Meta AI is surprisingly good, Zuck cooking fr", "positive"),
        ("Metaverse was a $50B mistake, at least they pivoted", "negative"),
        ("Instagram and WhatsApp printing money, core business strong", "positive"),
        ("Threads could be bigger than Twitter eventually", "positive"),
        ("Teen addiction lawsuits are serious liability risk", "negative"),
    ],
    "AMD": [
        ("AMD MI300X is legitimately competitive with H100", "positive"),
        ("Lisa Su is the best CEO in semiconductors, no debate", "positive"),
        ("AMD always disappoints at the last minute, be careful", "negative"),
        ("ROCm software stack is finally getting good", "positive"),
        ("AMD taking datacenter share from Intel not just gaming", "positive"),
    ],
}


# ── Sentiment analysis ────────────────────────────────────────────────────────
async def analyze_sentiment_groq(texts: list[str], ticker: str) -> dict:
    """Use Groq to analyze sentiment of news/posts."""
    if GROQ_AVAILABLE and groq_client:
        try:
            combined = "\n".join([f"- {t}" for t in texts[:8]])
            completion = groq_client.chat.completions.create(
                model="llama3-8b-8192",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze the sentiment of these {ticker} stock mentions. Return ONLY valid JSON.

Texts:
{combined}

Return exactly this JSON format:
{{"score": 0.72, "label": "Bullish", "confidence": 0.85, "summary": "one sentence summary", "positive_count": 5, "negative_count": 2, "neutral_count": 1}}

score is 0.0 (very bearish) to 1.0 (very bullish), 0.5 is neutral.
JSON only:"""
                }]
            )
            raw = completion.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            print(f"Groq sentiment error: {e}")

    # Rule-based fallback
    positive_words = ["surge", "beats", "record", "growth", "strong", "bullish", "moon", "printing", "insane", "great", "positive", "buy", "up", "gain", "win", "best", "love", "amazing"]
    negative_words = ["fall", "drop", "miss", "concern", "risk", "bearish", "down", "loss", "bad", "terrible", "sell", "decline", "cut", "layoff", "fine", "lawsuit", "recall"]

    pos = sum(1 for t in texts for w in positive_words if w in t.lower())
    neg = sum(1 for t in texts for w in negative_words if w in t.lower())
    total = pos + neg or 1
    score = round(0.5 + (pos - neg) / (total * 4), 3)
    score = max(0.1, min(0.95, score))
    label = "Bullish" if score > 0.6 else "Bearish" if score < 0.4 else "Neutral"

    return {
        "score": score,
        "label": label,
        "confidence": round(0.6 + random.random() * 0.3, 2),
        "summary": f"{ticker} showing {label.lower()} sentiment based on recent mentions.",
        "positive_count": pos,
        "negative_count": neg,
        "neutral_count": max(0, len(texts) - pos - neg),
    }


async def fetch_ticker_data(ticker: str) -> dict:
    """Fetch real or demo data for a ticker."""
    headlines = []
    posts = []

    # Try real NewsAPI if key available
    news_api_key = os.getenv("NEWS_API_KEY", "")
    if HTTPX_AVAILABLE and news_api_key:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://newsapi.org/v2/everything",
                    params={"q": ticker, "pageSize": 5, "sortBy": "publishedAt", "apiKey": news_api_key},
                    timeout=5
                )
                data = resp.json()
                headlines = [a["title"] for a in data.get("articles", [])[:5]]
        except Exception:
            pass

    # Try real Reddit if credentials available
    reddit_id = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    if REDDIT_AVAILABLE and reddit_id and reddit_secret:
        try:
            reddit = praw.Reddit(
                client_id=reddit_id,
                client_secret=reddit_secret,
                user_agent="StockIQ/1.0"
            )
            subreddit = reddit.subreddit("wallstreetbets+investing+stocks")
            for post in subreddit.search(ticker, limit=5, time_filter="day"):
                posts.append(post.title)
        except Exception:
            pass

    # Demo fallback
    if not headlines:
        demo = DEMO_HEADLINES.get(ticker, DEMO_HEADLINES["AAPL"])
        # Pick 3 random headlines
        selected = random.sample(demo, min(3, len(demo)))
        headlines = [h[0] for h in selected]

    if not posts:
        demo_posts = REDDIT_POSTS.get(ticker, REDDIT_POSTS["AAPL"])
        selected = random.sample(demo_posts, min(3, len(demo_posts)))
        posts = [p[0] for p in selected]

    all_texts = headlines + posts
    sentiment = await analyze_sentiment_groq(all_texts, ticker)

    # Simulate price movement based on sentiment
    base_prices = {"AAPL": 189, "TSLA": 245, "NVDA": 875, "MSFT": 415, "GOOGL": 175, "AMZN": 198, "META": 505, "AMD": 168}
    base = base_prices.get(ticker, 100)
    prev_score = ticker_scores.get(ticker, 0.5)
    price_change = (sentiment["score"] - 0.5) * 2 + random.uniform(-0.8, 0.8)
    current_price = round(base * (1 + price_change / 100), 2)

    ticker_scores[ticker] = sentiment["score"]

    return {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "price": current_price,
        "price_change": round(price_change, 2),
        "sentiment": sentiment,
        "headlines": headlines[:3],
        "reddit_posts": posts[:3],
        "volume": random.randint(15000000, 85000000),
        "mentions": random.randint(50, 500),
    }


# ── Background feed loop ──────────────────────────────────────────────────────
async def sentiment_feed_loop():
    global is_running
    is_running = True

    # Init history for all tickers
    for t in TRACKED_TICKERS:
        ticker_data[t] = deque(maxlen=50)
        ticker_scores[t] = 0.5

    while is_running:
        for ticker in TRACKED_TICKERS:
            if not connected_clients:
                await asyncio.sleep(2)
                continue
            try:
                data = await fetch_ticker_data(ticker)
                ticker_data[ticker].append(data)

                # Broadcast to all clients
                await broadcast_all("ticker_update", data)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Feed error for {ticker}: {e}")

        # Wait before next full cycle
        await asyncio.sleep(12)


async def broadcast_all(event: str, data: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json({"event": event, "data": data})
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


# ── REST endpoints ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(sentiment_feed_loop())


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "groq_available": GROQ_AVAILABLE,
        "reddit_available": REDDIT_AVAILABLE and bool(os.getenv("REDDIT_CLIENT_ID")),
        "news_available": bool(os.getenv("NEWS_API_KEY")),
        "mode": "live" if (REDDIT_AVAILABLE or bool(os.getenv("NEWS_API_KEY"))) else "demo",
        "tracked_tickers": TRACKED_TICKERS,
    }


@app.get("/api/tickers")
async def get_tickers():
    result = {}
    for ticker in TRACKED_TICKERS:
        history = list(ticker_data.get(ticker, []))
        result[ticker] = {
            "history": history[-20:],
            "latest": history[-1] if history else None,
            "score": ticker_scores.get(ticker, 0.5),
        }
    return result


@app.get("/api/tickers/{ticker}")
async def get_ticker(ticker: str):
    ticker = ticker.upper()
    if ticker not in TRACKED_TICKERS:
        return {"error": "Ticker not tracked"}
    history = list(ticker_data.get(ticker, []))
    return {
        "ticker": ticker,
        "history": history,
        "latest": history[-1] if history else None,
    }


@app.get("/api/snapshot")
async def snapshot():
    """Get current sentiment snapshot for all tickers."""
    results = []
    for ticker in TRACKED_TICKERS:
        data = await fetch_ticker_data(ticker)
        ticker_data[ticker] = ticker_data.get(ticker, deque(maxlen=50))
        ticker_data[ticker].append(data)
        results.append(data)
    return results


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)

    try:
        # Send current snapshot on connect
        await websocket.send_json({"event": "connected", "data": {"tickers": TRACKED_TICKERS}})

        # Send existing history
        for ticker in TRACKED_TICKERS:
            history = list(ticker_data.get(ticker, []))
            if history:
                await websocket.send_json({
                    "event": "ticker_history",
                    "data": {"ticker": ticker, "history": history[-10:]}
                })

        # Keep alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping", "data": {}})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error: {e}")
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
