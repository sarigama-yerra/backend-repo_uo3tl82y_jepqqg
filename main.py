import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Article as ArticleSchema, Launch as LaunchSchema

app = FastAPI(title="Grid7 API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ArticlesResponse(BaseModel):
    items: List[ArticleSchema]
    total: int
    refreshed_at: datetime


class LaunchesResponse(BaseModel):
    items: List[LaunchSchema]
    total: int


CATEGORY_SET = {"AI", "OS", "Gadgets", "Other"}

# --- Live Tech RSS Sources (no API keys needed) ---
TECH_FEEDS = [
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Ars Technica", "http://feeds.arstechnica.com/arstechnica/index"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
]

KEYWORD_TO_CATEGORY = {
    "ai": "AI",
    "artificial intelligence": "AI",
    "machine learning": "AI",
    "linux": "OS",
    "windows": "OS",
    "android": "OS",
    "ios": "OS",
    "macos": "OS",
    "iphone": "Gadgets",
    "ipad": "Gadgets",
    "watch": "Gadgets",
    "laptop": "Gadgets",
    "phone": "Gadgets",
    "camera": "Gadgets",
}


def _infer_category(text: str) -> str:
    t = (text or "").lower()
    for kw, cat in KEYWORD_TO_CATEGORY.items():
        if kw in t:
            return cat
    return "Other"


def fetch_live_articles(max_per_feed: int = 15) -> List[ArticleSchema]:
    items: List[ArticleSchema] = []
    for source, url in TECH_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", getattr(entry, "description", ""))
                link = getattr(entry, "link", None)
                # Published date parsing
                published = None
                if getattr(entry, "published_parsed", None):
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif getattr(entry, "updated_parsed", None):
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                category = _infer_category(f"{title} {summary}")
                art = ArticleSchema(
                    source=source,
                    category=category,
                    headline=title[:240] if title else "Untitled",
                    summary=(summary or "").replace("<p>", " ").replace("</p>", " ").strip()[:600],
                    content=None,
                    links=[link] if link else None,
                    published_at=published,
                )
                items.append(art)
        except Exception:
            continue
    # Sort by time desc, keep latest 60
    items.sort(key=lambda a: a.published_at or datetime.now(timezone.utc), reverse=True)
    return items[:60]


def ensure_seed_data():
    """Seed a minimal set of demo content if collections are empty."""
    try:
        # Seed Launches only; articles will be live-fetched
        if db and db["launch"].count_documents({}) == 0:
            base = datetime.now(timezone.utc)
            seed_launches: List[LaunchSchema] = [
                LaunchSchema(
                    title="NeuroNet 2.0",
                    description="A major AI model refresh with explainable reasoning.",
                    date=base + timedelta(days=5),
                    tag="AI",
                    link="https://example.com/neuronet",
                ),
                LaunchSchema(
                    title="Kernel 6.2 LTS",
                    description="Long-term support kernel for enterprise systems.",
                    date=base + timedelta(days=12),
                    tag="OS",
                    link="https://example.com/kernel",
                ),
                LaunchSchema(
                    title="Aurora Fold X",
                    description="A durable foldable with a near-invisible crease.",
                    date=base + timedelta(days=21),
                    tag="Gadgets",
                    link="https://example.com/aurora",
                ),
                LaunchSchema(
                    title="OrbitalLink",
                    description="Affordable, modular satellite buses for startups.",
                    date=base + timedelta(days=34),
                    tag="Other",
                    link="https://example.com/orbitallink",
                ),
            ]
            for ln in seed_launches:
                create_document("launch", ln)
    except Exception:
        pass


@app.on_event("startup")
async def startup_event():
    ensure_seed_data()
    # Warm the cache with live articles if DB is configured and empty
    try:
        if db and db["article"].count_documents({}) == 0:
            for art in fetch_live_articles():
                create_document("article", art)
    except Exception:
        pass


@app.get("/")
def root():
    return {"name": "Grid7 API", "status": "ok"}


@app.get("/api/articles", response_model=ArticlesResponse)
def get_articles(
    category: Optional[str] = Query(default=None, description="AI | OS | Gadgets | Other"),
    limit: int = Query(default=40, ge=1, le=200),
):
    ensure_seed_data()

    # Try DB first
    items: List[ArticleSchema] = []
    total = 0
    try:
        filter_dict = {}
        if category and category in CATEGORY_SET:
            filter_dict["category"] = category
        docs = get_documents("article", filter_dict=filter_dict, limit=limit)
        total = db["article"].count_documents(filter_dict) if db else len(docs)
        for d in docs:
            d.pop("_id", None)
            items.append(ArticleSchema(**d))
    except Exception:
        # If DB isn't available, fall back to live fetch
        items = fetch_live_articles(max_per_feed=15)
        if category and category in CATEGORY_SET:
            items = [a for a in items if a.category == category]
        total = len(items)
        items = items[:limit]

    # Sort by newest
    items.sort(key=lambda a: a.published_at or datetime.now(timezone.utc), reverse=True)
    return ArticlesResponse(items=items, total=total, refreshed_at=datetime.now(timezone.utc))


@app.get("/api/launches", response_model=LaunchesResponse)
def get_launches(limit: int = Query(default=30, ge=1, le=200)):
    ensure_seed_data()
    items = []
    total = 0
    try:
        docs = get_documents("launch", limit=limit)
        total = db["launch"].count_documents({}) if db else len(docs)
        for d in docs:
            d.pop("_id", None)
            items.append(LaunchSchema(**d))
    except Exception:
        items = []
        total = 0

    return LaunchesResponse(items=items, total=total)


@app.post("/api/refresh")
def trigger_refresh():
    """
    Refresh endpoint: fetches fresh articles from RSS feeds and stores them if DB is available.
    Always returns the current timestamp; frontend can show spinner while it reloads.
    """
    refreshed_at = datetime.now(timezone.utc)
    try:
        live_items = fetch_live_articles()
        if db:
            # simple strategy: clear and re-insert recent
            db["article"].delete_many({})
            for art in live_items:
                create_document("article", art)
    except Exception:
        pass
    return {"status": "ok", "refreshed_at": refreshed_at}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
