from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse
from app.schemas.enums import LeadPriority, LeadSource, LeadStatus


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=300)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    score: int = Field(0, ge=0, le=100)
    status: LeadStatus = LeadStatus.nuevo
    priority: LeadPriority = LeadPriority.media
    issues: list[str] = Field(default_factory=list)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)
    google_place_id: Optional[str] = Field(None, max_length=200)
    source: LeadSource = LeadSource.manual
    last_contact: Optional[date] = None
    is_viewed: bool = False


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=300)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    score: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[LeadStatus] = None
    priority: Optional[LeadPriority] = None
    issues: Optional[list[str]] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)
    last_contact: Optional[date] = None
    is_viewed: Optional[bool] = None
    ai_analysis: Optional[str] = None
    social_profiles: Optional[list[dict]] = None


class LeadResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    category: str
    location: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    score: int
    status: LeadStatus
    priority: LeadPriority
    issues: list[str]
    phone: Optional[str] = None
    website: Optional[str] = None
    google_place_id: Optional[str] = None
    source: LeadSource
    last_contact: Optional[date] = None
    ai_analysis: Optional[str] = None
    social_profiles: Optional[list[dict]] = None
    is_viewed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


_SORTABLE_FIELDS = {"name", "score", "status", "priority", "created_at", "updated_at"}


class LeadFilters(BaseModel):
    q: Optional[str] = Field(None, max_length=200)
    status: Optional[LeadStatus] = None
    priority: Optional[LeadPriority] = None
    category: Optional[str] = Field(None, max_length=100)
    min_score: Optional[int] = Field(None, ge=0, le=100)
    max_score: Optional[int] = Field(None, ge=0, le=100)
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")
    is_viewed: Optional[bool] = None

    @property
    def safe_sort_by(self) -> str:
        return self.sort_by if self.sort_by in _SORTABLE_FIELDS else "created_at"


class LeadListResponse(PaginatedResponse[LeadResponse]):
    pass


class LeadQualityItem(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    website: Optional[str] = None
    category: str
    score: int = 0


class LeadQualityCheckRequest(BaseModel):
    leads: list[LeadQualityItem]


class LeadQualityCheckResponse(BaseModel):
    junk_ids: list[str]
