from dataclasses import dataclass

PAGESPEED_THRESHOLD = 50


@dataclass(frozen=True)
class _Rule:
    risk: int
    issue: str


_NO_WEBSITE = _Rule(risk=35, issue="Sin sitio web")
_NO_PHONE = _Rule(risk=15, issue="Sin telefono registrado")
_NO_RATING = _Rule(risk=15, issue="Sin calificaciones")
_NO_SSL = _Rule(risk=15, issue="Sitio web sin SSL")
_LOW_PAGESPEED = _Rule(risk=20, issue="Rendimiento web bajo")
_INCOMPLETE_GMB = _Rule(risk=20, issue="Perfil de Google Business incompleto")


def calculate_score(
    has_website: bool,
    has_phone: bool,
    has_rating: bool,
    website_has_ssl: bool,
    pagespeed_score: int | None,
    has_complete_google_business: bool,
) -> tuple[int, list[str]]:
    checks: list[tuple[bool, _Rule]] = [
        (not has_website, _NO_WEBSITE),
        (not has_phone, _NO_PHONE),
        (not has_rating, _NO_RATING),
        (has_website and not website_has_ssl, _NO_SSL),
        (pagespeed_score is not None and pagespeed_score < PAGESPEED_THRESHOLD, _LOW_PAGESPEED),
        (not has_complete_google_business, _INCOMPLETE_GMB),
    ]

    risk = 0
    issues: list[str] = []
    for condition, rule in checks:
        if condition:
            risk += rule.risk
            issues.append(rule.issue)

    return max(0, 100 - risk), issues
