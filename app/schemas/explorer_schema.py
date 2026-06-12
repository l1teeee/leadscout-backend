import re

from pydantic import BaseModel, Field, field_validator

_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _strip_controls(v: str | None) -> str | None:
    if v is None:
        return None
    return _CONTROL_RE.sub(" ", v).strip() or None


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
    business_context: str | None = Field(None, max_length=2000)

    @field_validator("name", "category", "location", "business_context", mode="before")
    @classmethod
    def sanitize_fields(cls, v: str | None) -> str | None:
        return _strip_controls(v)


class LeadAnalyzeResponse(BaseModel):
    analysis: str
    social_profiles: list[dict[str, str]] = Field(default_factory=list)


class LeadChatRequest(BaseModel):
    name: str = Field(..., max_length=300)
    category: str = Field("", max_length=100)
    location: str = Field("", max_length=300)
    phone: str | None = None
    website: str | None = None
    score: int = Field(0, ge=0, le=100)
    issues: list[str] = []
    lead_id: str | None = None
    analysis: str | None = None
    question: str = Field(..., min_length=1, max_length=600)
    business_context: str | None = Field(None, max_length=2000)

    @field_validator("name", "category", "location", "question", "business_context", mode="before")
    @classmethod
    def sanitize_fields(cls, v: str | None) -> str | None:
        return _strip_controls(v)


class LeadChatResponse(BaseModel):
    answer: str


class OutreachRequest(BaseModel):
    name: str = Field(..., max_length=300)
    category: str = Field("", max_length=100)
    location: str = Field("", max_length=300)
    phone: str | None = None
    website: str | None = None
    score: int = Field(0, ge=0, le=100)
    issues: list[str] = []
    platform: str = Field(..., max_length=50)
    lead_id: str | None = None
    social_profiles: list[dict] = Field(default_factory=list)
    business_context: str | None = Field(None, max_length=2000)

    @field_validator("name", "category", "location", "platform", "business_context", mode="before")
    @classmethod
    def sanitize_fields(cls, v: str | None) -> str | None:
        return _strip_controls(v)


class OutreachResponse(BaseModel):
    message: str
    platform: str
