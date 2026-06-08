from pydantic import BaseModel, Field


class ExplorerSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=300)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    radius_km: float = Field(2.0, ge=0.5, le=50.0)
    category: str = Field("General", max_length=100)


class ExplorerResultItem(BaseModel):
    google_place_id: str
    name: str
    category: str
    address: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    website: str | None = None
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
    phone: str | None = None
    website: str | None = None
    score: int = Field(0, ge=0, le=100)
    issues: list[str] = []
    lead_id: str | None = None
    force_refresh: bool = False


class LeadAnalyzeResponse(BaseModel):
    analysis: str
