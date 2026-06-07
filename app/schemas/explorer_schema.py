from typing import Optional

from pydantic import BaseModel, Field


class ExplorerSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=300)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: float = Field(2.0, ge=0.5, le=50.0)
    category: str = Field("General", max_length=100)


class ExplorerResultItem(BaseModel):
    google_place_id: str
    name: str
    category: str
    address: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    score: int = Field(..., ge=0, le=100)
    issues: list[str]
    already_saved: bool


class ExplorerSearchResponse(BaseModel):
    results: list[ExplorerResultItem]
    total: int
    saved_new: int


class LeadAnalyzeRequest(BaseModel):
    name: str = Field(..., max_length=300)
    category: str = Field("", max_length=100)
    location: str = Field("", max_length=300)
    phone: Optional[str] = None
    website: Optional[str] = None
    score: int = Field(0, ge=0, le=100)
    issues: list[str] = []


class LeadAnalyzeResponse(BaseModel):
    analysis: str
