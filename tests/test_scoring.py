from app.services.scoring_service import calculate_score, PAGESPEED_THRESHOLD


def test_perfect_score():
    score, issues = calculate_score(
        has_website=True,
        has_phone=True,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=80,
        has_complete_google_business=True,
    )
    assert score == 100
    assert issues == []


def test_no_website_adds_35():
    score, issues = calculate_score(
        has_website=False,
        has_phone=True,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=80,
        has_complete_google_business=True,
    )
    assert score == 100 - 35
    assert "Sin sitio web" in issues


def test_no_phone_adds_15():
    score, issues = calculate_score(
        has_website=True,
        has_phone=False,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=80,
        has_complete_google_business=True,
    )
    assert score == 100 - 15
    assert "Sin telefono registrado" in issues


def test_no_ssl_adds_15():
    score, issues = calculate_score(
        has_website=True,
        has_phone=True,
        has_rating=True,
        website_has_ssl=False,
        pagespeed_score=80,
        has_complete_google_business=True,
    )
    assert score == 100 - 15
    assert "Sitio web sin SSL" in issues


def test_ssl_not_checked_without_website():
    score, issues = calculate_score(
        has_website=False,
        has_phone=True,
        has_rating=True,
        website_has_ssl=False,
        pagespeed_score=80,
        has_complete_google_business=True,
    )
    # SSL penalty only applies when has_website=True
    assert "Sitio web sin SSL" not in issues


def test_low_pagespeed_adds_20():
    score, issues = calculate_score(
        has_website=True,
        has_phone=True,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=PAGESPEED_THRESHOLD - 1,
        has_complete_google_business=True,
    )
    assert score == 100 - 20
    assert "Rendimiento web bajo" in issues


def test_pagespeed_none_skipped():
    score, issues = calculate_score(
        has_website=True,
        has_phone=True,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=None,
        has_complete_google_business=True,
    )
    assert "Rendimiento web bajo" not in issues


def test_incomplete_gmb_adds_20():
    score, issues = calculate_score(
        has_website=True,
        has_phone=True,
        has_rating=True,
        website_has_ssl=True,
        pagespeed_score=80,
        has_complete_google_business=False,
    )
    assert score == 100 - 20
    assert "Perfil de Google Business incompleto" in issues


def test_score_clamped_to_zero():
    score, _ = calculate_score(
        has_website=False,
        has_phone=False,
        has_rating=False,
        website_has_ssl=False,
        pagespeed_score=10,
        has_complete_google_business=False,
    )
    assert score == 0


def test_all_issues_accumulate():
    score, issues = calculate_score(
        has_website=False,
        has_phone=False,
        has_rating=False,
        website_has_ssl=False,
        pagespeed_score=10,
        has_complete_google_business=False,
    )
    assert len(issues) == 5
    assert score == 0
