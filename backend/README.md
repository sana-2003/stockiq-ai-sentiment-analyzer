# 📈 StockIQ — Real-Time Stock Sentiment Analyzer

> **Portfolio Project** | Reddit + News → Groq AI sentiment scoring → Live WebSocket dashboard with charts

---

## 🏗 Architecture

```
Reddit API + NewsAPI
        │
        ▼
FastAPI Backend (main.py)
  ├── Scraper loop (every 12s per ticker)
  ├── Groq AI sentiment scoring (Llama3-8b)
  ├── WebSocket broadcaster
  └── REST API /api/tickers
        │
        │ WebSocket events: ticker_update | ticker_history
        ▼
Frontend Dashboard (index.html)
  ├── Live sentiment chart (Chart.js)
  ├── Heatmap (8 tickers)
  ├── Market bar with sparklines
  ├── News + Reddit feed
  └── Real-time signal feed
```

---

## ⚡ Quick Start

```bash
cd stockiq/backend
pip install fastapi "uvicorn[standard]" pydantic httpx groq
export GROQ_API_KEY=your_key_here
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
cd stockiq/frontend
python3 -m http.server 3001
```

Open: **http://localhost:3001**

---

## 🔧 Real Data Setup (Optional)

### NewsAPI (free tier: 100 requests/day)
1. Sign up at **newsapi.org**
2. Get free API key
3. `export NEWS_API_KEY=your_key`

### Reddit API (free)
1. Go to **reddit.com/prefs/apps**
2. Create app → script type
3. `export REDDIT_CLIENT_ID=your_id`
4. `export REDDIT_CLIENT_SECRET=your_secret`

Without these, the app runs in **demo mode** with realistic simulated data.

---

## 💼 Interview Talking Points

**"How does the sentiment scoring work?"**
> Each cycle fetches 3-5 news headlines and 3-5 Reddit posts per ticker, combines them into a prompt, and sends to Groq's Llama3-8b model. The model returns a structured JSON with a 0-1 score, label, and confidence. We use Pydantic to validate and fall back to rule-based keyword matching if Groq fails.

**"How does real-time work?"**
> The backend runs an async loop that cycles through 8 tickers every 12 seconds. Each update is broadcast to all connected WebSocket clients instantly. The frontend maintains a 50-point rolling history per ticker for the chart.

**"How would you scale this?"**
> Redis pub/sub for multi-replica WebSocket fan-out. Celery workers for parallel ticker processing. PostgreSQL for historical storage. Rate limiting on NewsAPI calls. Caching sentiment scores for 60s to avoid redundant API calls.

---

## 📄 License
MIT
