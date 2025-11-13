import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Article as ArticleSchema, Launch as LaunchSchema

app = FastAPI(title="Grid7 API", version="1.0.0")

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


def ensure_seed_data():
    """Seed a minimal set of demo content if collections are empty."""
    try:
        # Seed Articles
        if db and db["article"].count_documents({}) == 0:
            seed_articles: List[ArticleSchema] = [
                ArticleSchema(
                    source="The Verge",
                    category="AI",
                    headline="OpenAI unveils next-gen reasoning model",
                    summary="A new model focuses on tool-use and faithful reasoning with improved transparency.",
                    content=(
                        "OpenAI announced a next-generation model with better reasoning, tool-use, and safety. "
                        "It aims to provide more grounded answers and integrates with partner ecosystems."
                    ),
                    links=["https://openai.com"],
                    published_at=datetime.now(timezone.utc) - timedelta(hours=3),
                ),
                ArticleSchema(
                    source="Ars Technica",
                    category="OS",
                    headline="Linux 6.x brings performance wins across the board",
                    summary="The latest kernel release includes scheduler improvements and I/O optimizations.",
                    content=(
                        "Linux 6.x introduces notable performance improvements on desktop and server workloads, "
                        "with enhanced power management and filesystem updates."
                    ),
                    links=["https://arstechnica.com"],
                    published_at=datetime.now(timezone.utc) - timedelta(hours=6),
                ),
                ArticleSchema(
                    source="Engadget",
                    category="Gadgets",
                    headline="A foldable that actually feels durable",
                    summary="Early hands-on suggests improved hinge design and fewer display creases.",
                    content=(
                        "The latest foldable phone iteration focuses on durability with a redesigned hinge and "
                        "enhanced protective layers, aiming to reduce creases and improve lifespan."
                    ),
                    links=["https://engadget.com"],
                    published_at=datetime.now(timezone.utc) - timedelta(hours=12),
                ),
                ArticleSchema(
                    source="TechCrunch",
                    category="Other",
                    headline="Startup raises funding to build modular satellites",
                    summary="Aerospace startup lands Series B to scale modular satellite platforms.",
                    content=(
                        "The company plans to accelerate development of modular satellite buses, enabling faster "
                        "deployment and lower costs for a range of orbital missions."
                    ),
                    links=["https://techcrunch.com"],
                    published_at=datetime.now(timezone.utc) - timedelta(days=1, hours=2),
                ),
            ]
            for art in seed_articles:
                create_document("article", art)

        # Seed Launches
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
        # If database isn't configured, skip silently (endpoints will still work with empty results)
        pass


@app.on_event("startup")
async def startup_event():
    ensure_seed_data()


@app.get("/")
def root():
    return {"name": "Grid7 API", "status": "ok"}


@app.get("/api/articles", response_model=ArticlesResponse)
def get_articles(
    category: Optional[str] = Query(default=None, description="AI | OS | Gadgets | Other"),
    limit: int = Query(default=40, ge=1, le=200),
):
    ensure_seed_data()
    filter_dict = {}
    if category and category in CATEGORY_SET:
        filter_dict["category"] = category

    items = []
    total = 0
    try:
        docs = get_documents("article", filter_dict=filter_dict, limit=limit)
        total = db["article"].count_documents(filter_dict) if db else len(docs)
        # Convert Mongo docs to ArticleSchema
        for d in docs:
            # Clean _id and timestamps
            d.pop("_id", None)
            items.append(ArticleSchema(**d))
    except Exception:
        # If DB isn't available, return empty
        items = []
        total = 0

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
    Placeholder refresh endpoint. In a production scenario, this would re-fetch
    content from external sources. Here it simply returns a timestamp that the
    frontend can use to show a spinner.
    """
    return {"status": "ok", "refreshed_at": datetime.now(timezone.utc)}


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
