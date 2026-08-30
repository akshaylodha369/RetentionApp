import os

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

if not GOOGLE_PLACES_API_KEY:
    raise RuntimeError(
        "GOOGLE_PLACES_API_KEY environment variable is not set"
    )