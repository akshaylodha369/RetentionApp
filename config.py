import os

GOOGLE_PLACES_API_KEY = os.getenv("AIzaSyB7WpHGa_IvxV4LCbh0K4p0kvDZaUZ3Gjg")

if not GOOGLE_PLACES_API_KEY:
    raise RuntimeError(
        "GOOGLE_PLACES_API_KEY environment variable is not set"
    )