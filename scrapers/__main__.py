"""Allow `python -m scrapers.gmaps` via package redirect — prefer module path."""
from scrapers.gmaps import main

if __name__ == "__main__":
    main()
