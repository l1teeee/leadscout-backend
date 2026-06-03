from typing import Optional

from pydantic import BaseModel


class WorkspaceSettings(BaseModel):
    id: str
    name: str
    slug: str
    country: str
    timezone: str
    currency: str


class TeamMember(BaseModel):
    id: str
    full_name: str
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
