from typing import Optional

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    role: str
    is_active: bool


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
