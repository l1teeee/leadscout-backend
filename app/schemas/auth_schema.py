from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)


class ResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class OnboardingRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, max_length=100)
    workspace_name: Optional[str] = Field(None, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)


class ApproximateLocationRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    label: Optional[str] = Field(None, max_length=200)


class AuthUser(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str = "viewer"
    onboarded: bool = False
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    approximate_latitude: Optional[float] = None
    approximate_longitude: Optional[float] = None
    approximate_location_label: Optional[str] = None
    user_signature: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


class MessageResponse(BaseModel):
    message: str
