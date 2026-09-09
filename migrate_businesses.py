import os
import requests
from database import get_businesses

URL = "https://retentionapp.onrender.com/api/admin/migrate-businesses"

secret = os.environ.get("BUSINESS_MIGRATION_SECRET")

if not secret:
    raise SystemExit("BUSINESS_MIGRATION_SECRET is not set.")

rows = get_businesses()

businesses = []

for row in rows:
    businesses.append({
        "name": row[1],
        "category": row[2],
        "latitude": row[3],
        "longitude": row[4],
        "address": row[5],
        "offer": row[6]
    })

print(f"Local businesses found: {len(businesses)}")

response = requests.post(
    URL,
    headers={
        "X-Migration-Secret": secret
    },
    json={
        "businesses": businesses
    },
    timeout=60
)

print("Status:", response.status_code)
print("Response:", response.text)