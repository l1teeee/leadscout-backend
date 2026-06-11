from typing import Optional

from pydantic import BaseModel, Field


class WorkspaceSettings(BaseModel):
    id: str
    name: str
    slug: str
    country: str
    industry: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    timezone: str = "UTC"
    currency: str = "USD"


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)
    timezone: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=10)


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, max_length=100)


class TeamMember(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: str
    role: str
    avatar_url: Optional[str] = None


class TeamSettings(BaseModel):
    members: list[TeamMember]


class UsageSettings(BaseModel):
    plan: str
    searches_used: int
    searches_limit: int
    tokens_used: int
    tokens_limit: int


class AuditEntry(BaseModel):
    query: Optional[str] = None
    location: Optional[str] = None
    category: Optional[str] = None
    results_count: int = 0
    created_at: Optional[str] = None


class AuditSettings(BaseModel):
    entries: list[AuditEntry]


class AiContextSettings(BaseModel):
    business_context: str = ""
    constraints: str = ""
    updated_at: Optional[str] = None


class AiContextUpdate(BaseModel):
    business_context: Optional[str] = Field(None, max_length=1000)
    constraints: Optional[str] = Field(None, max_length=800)
