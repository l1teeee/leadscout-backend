from enum import Enum


class LeadStatus(str, Enum):
    nuevo = "nuevo"
    contactado = "contactado"
    calificado = "calificado"
    perdido = "perdido"
    desvinculado = "desvinculado"


class LeadPriority(str, Enum):
    alta = "alta"
    media = "media"
    baja = "baja"


class LeadSource(str, Enum):
    manual = "manual"
    explorer = "explorer"


class UserRole(str, Enum):
    owner = "owner"
    admin = "admin"
    sales = "sales"
    analyst = "analyst"
    viewer = "viewer"


class ActivityType(str, Enum):
    created = "created"
    status_changed = "status_changed"
    note_added = "note_added"
    contacted = "contacted"
    qualified = "qualified"
    lost = "lost"
