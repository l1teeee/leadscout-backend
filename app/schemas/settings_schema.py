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
    leads_used: int
    leads_limit: int
    searches_used: int
    searches_limit: int
    api_calls_used: int
    api_calls_limit: int
