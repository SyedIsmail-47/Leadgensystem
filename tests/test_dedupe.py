from scrapers.dedupe import dedupe_key


def test_dedupe_same_phone():
    a = dedupe_key("Smile Dental Clinic", "+92 300 1234567", None)
    b = dedupe_key("Smile Dental Clinic", "03001234567", None)
    assert a.split("|")[0] == b.split("|")[0]


def test_dedupe_domain():
    a = dedupe_key("Acme", None, "https://www.acme.com/about")
    b = dedupe_key("Acme", None, "http://acme.com")
    assert a == b
