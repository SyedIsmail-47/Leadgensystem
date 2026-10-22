.PHONY: test test-unit test-int test-e2e lint

test:
	pytest -q

test-unit:
	pytest -q -m unit

test-int:
	pytest -q -m integration

test-e2e:
	pytest -q -m e2e

lint:
	ruff check common enrich scoring scrapers outreach worker dashboard tests || true
