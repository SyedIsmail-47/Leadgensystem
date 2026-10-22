from unittest.mock import patch

import pytest

from common.urls import normalize_url
from enrich.validators import normalize_phone, validate_email
from scrapers.dedupe import dedupe_key
from scrapers.website import extract_emails


@pytest.mark.unit
def test_B1_dedupe_key_phone_variants():
    a = dedupe_key("Smile Dental Clinic ", "+92 300 1234567")
    b = dedupe_key("smile dental clinic", "03001234567")
    assert a == b


@pytest.mark.unit
def test_B2_dedupe_key_domain_when_no_phone():
    a = dedupe_key("Acme", None, "https://www.site.com/")
    b = dedupe_key("Acme", None, "http://site.com")
    assert a == b


@pytest.mark.unit
def test_B3_phone_normalize_pk():
    phone, ok = normalize_phone("0300-1234567", "PK")
    assert ok and phone == "+923001234567"
    phone2, ok2 = normalize_phone("abc", "PK")
    assert phone2 is None and ok2 is False


@pytest.mark.unit
def test_B4_email_extraction_filters():
    html = """
    <a href="mailto:hello@clinic.com">x</a>
    team@clinic.com
    logo@2x.png
    sprite@3x.webp
    example@example.com
    """
    emails = extract_emails(html)
    assert "hello@clinic.com" in emails
    assert "team@clinic.com" in emails
    assert "example@example.com" not in emails
    assert not any(e.endswith((".png", ".webp")) for e in emails)


@pytest.mark.unit
def test_B5_obfuscated_email():
    emails = extract_emails("reach us at info [at] site [dot] com please")
    assert "info@site.com" in emails


@pytest.mark.unit
def test_B6_email_validation_mx_mocked():
    email, mx = validate_email("a@b")
    assert email is None

    with patch("enrich.validators.dns.resolver.resolve", side_effect=Exception("nxdomain")):
        email2, mx2 = validate_email("user@valid-domain.com")
        assert email2 == "user@valid-domain.com"
        assert mx2 is False


@pytest.mark.unit
def test_B7_url_normalization():
    u = normalize_url("site.com/path?utm_source=x&id=1#frag")
    assert u.startswith("https://")
    assert "utm_source" not in u
    assert "#frag" not in u
    assert "id=1" in u
