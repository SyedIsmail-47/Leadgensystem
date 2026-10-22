from enrich.validators import normalize_phone, validate_email
from scrapers.website import extract_emails


def test_validate_email_syntax():
    email, _mx = validate_email("not-an-email")
    assert email is None


def test_normalize_phone_pk():
    phone, ok = normalize_phone("03001234567", "PK")
    assert ok
    assert phone and phone.startswith("+92")


def test_extract_emails_drops_images():
    html = '''
    <a href="mailto:hello@clinic.com">email</a>
    contact@clinic.com
    logo@cdn.com.png
    '''
    emails = extract_emails(html)
    assert "hello@clinic.com" in emails
    assert "contact@clinic.com" in emails
    assert not any(e.endswith(".png") for e in emails)
