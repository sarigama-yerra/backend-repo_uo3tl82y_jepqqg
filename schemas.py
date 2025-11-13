"""
Database Schemas for Grid7

Each Pydantic model corresponds to a MongoDB collection whose name is the lowercase
of the class name. For example: Article -> "article", Launch -> "launch".
"""
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

class Article(BaseModel):
    """
    Tech news article schema
    Collection: "article"
    """
    source: str = Field(..., description="Publisher name e.g., The Verge")
    category: str = Field(..., description="AI | OS | Gadgets | Other")
    headline: str = Field(..., description="Article headline")
    summary: str = Field(..., description="Concise 2-3 sentence brief")
    content: Optional[str] = Field(None, description="Full article text or extended brief")
    links: Optional[List[HttpUrl]] = Field(default=None, description="Source/grounding links")
    published_at: Optional[datetime] = Field(default=None, description="Original publish time")

class Launch(BaseModel):
    """
    Upcoming tech launch / milestone
    Collection: "launch"
    """
    title: str = Field(..., description="Launch title")
    description: str = Field(..., description="Short description of the launch")
    date: datetime = Field(..., description="Planned date/time of launch or milestone")
    tag: str = Field(..., description="Category tag e.g., AI | OS | Gadgets | Other")
    link: Optional[HttpUrl] = Field(default=None, description="Reference link")
