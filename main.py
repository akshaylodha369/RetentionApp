from fastapi import FastAPI, HTTPException, Form, Response, Cookie, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import hashlib
import hmac
import os
import re
import secrets
import time
import requests
import sqlite3

from database import (
    init_db,
    get_businesses,
    add_businesses,
    get_nearby_businesses,
    is_following,
    get_followed_businesses,
    get_connection,
    get_user_by_email,
    get_user_by_id,
    create_owner,
    get_owner_businesses,
    get_business_by_id,
    update_business_offer,
    create_business_claim_request,
    get_business_claim_requests,
    review_business_claim_request,
    get_pending_business_claim_requests,
    create_session as db_create_session,
    get_session_user_id,
    delete_session,
    delete_expired_sessions,
)

from config import GOOGLE_PLACES_API_KEY


# =========================================================
# APP
# =========================================================

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# Optional allowlist: comma-separated trusted origins, e.g. https://example.com.
# Requests without Origin (normal same-origin browser navigation and CLI tests) remain allowed.
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}


@app.middleware("http")
async def protect_unsafe_cross_origin_requests(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin:
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            scheme = forwarded_proto.split(",", 1)[0].strip() or request.url.scheme
            host = request.headers.get("host", "")
            expected_origin = f"{scheme}://{host}".rstrip("/")
            normalized_origin = origin.rstrip("/")
            if normalized_origin != expected_origin and normalized_origin not in ALLOWED_ORIGINS:
                return Response(
                    content='{"detail":"Cross-origin request blocked."}',
                    status_code=403,
                    media_type="application/json",
                )
    return await call_next(request)


init_db()


# =========================================================
# SECURITY / PASSWORDS
# =========================================================

PASSWORD_ITERATIONS = 100000

SESSION_MAX_AGE = 60 * 60 * 24 * 30

SESSION_COOKIE_NAME = "session"

IS_PRODUCTION = os.environ.get(
    "RENDER"
) == "true" or os.environ.get(
    "ENVIRONMENT",
    ""
).lower() == "production"


def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS
    )

    return salt.hex() + ":" + password_hash.hex()


def verify_password(password, stored_hash):

    try:

        salt_hex, hash_hex = stored_hash.split(":", 1)

        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_ITERATIONS
        )

        return secrets.compare_digest(
            actual_hash,
            expected_hash
        )

    except Exception:

        return False


# =========================================================
# ROLE-AWARE USER LOOKUP
# =========================================================

def get_user_by_email_and_role(
    email,
    role
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            email,
            password_hash,
            role
        FROM users
        WHERE email = ?
        AND role = ?
        LIMIT 1
        """,
        (
            email,
            role
        )
    )

    user = cursor.fetchone()

    conn.close()

    return user


# =========================================================
# SESSION HELPERS
# =========================================================

def create_secure_session(
    user_id
):

    raw_token = secrets.token_urlsafe(48)

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    now = int(time.time())

    expires_at = now + SESSION_MAX_AGE

    db_create_session(
        token_hash,
        user_id,
        expires_at,
        now
    )

    return raw_token


def get_current_user(
    session
):

    if not session:
        return None

    token_hash = hashlib.sha256(
        session.encode("utf-8")
    ).hexdigest()

    user_id = get_session_user_id(
        token_hash,
        int(time.time())
    )

    if not user_id:
        return None

    return get_user_by_id(
        user_id
    )


def require_login(
    session
):

    user = get_current_user(
        session
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Please login first."
        )

    return user


def require_owner(
    session
):

    user = require_login(
        session
    )

    if user[3] != "owner":

        raise HTTPException(
            status_code=403,
            detail="Owner access required."
        )

    return user


def set_session_cookie(
    response,
    token
):

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,
        max_age=SESSION_MAX_AGE,
        path="/"
    )


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return FileResponse(
        "static/index.html"
    )


# =========================================================
# CUSTOMER SIGNUP
# =========================================================

@app.post("/api/signup")
def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):

    name = name.strip()
    email = email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address."
        )

    if not name:

        raise HTTPException(
            status_code=400,
            detail="Name is required."
        )

    if not email:

        raise HTTPException(
            status_code=400,
            detail="Email is required."
        )

    if len(password) < 8:

        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters."
        )

    existing_customer = get_user_by_email_and_role(
        email,
        "customer"
    )

    if existing_customer:

        raise HTTPException(
            status_code=400,
            detail="Customer account already exists for this email."
        )

    password_hash = hash_password(
        password
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password_hash,
                role
            )
            VALUES (?, ?, ?, 'customer')
            """,
            (
                name,
                email,
                password_hash
            )
        )

        user_id = cursor.lastrowid

        conn.commit()

    except Exception:

        conn.rollback()
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Could not create customer account."
        )

    conn.close()

    return {
        "success": True,
        "user_id": user_id,
        "role": "customer"
    }


# =========================================================
# CUSTOMER LOGIN
# =========================================================

@app.post("/api/login")
def login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...)
):

    email = email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address."
        )

    user = get_user_by_email_and_role(
        email,
        "customer"
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid customer email or password."
        )

    if not verify_password(
        password,
        user[3]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid customer email or password."
        )

    token = create_secure_session(
        user[0]
    )

    set_session_cookie(
        response,
        token
    )

    return {
        "success": True,
        "user": {
            "id": user[0],
            "name": user[1],
            "email": user[2],
            "role": user[4]
        }
    }


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/api/me")
def me(
    session: str | None = Cookie(default=None)
):

    user = get_current_user(
        session
    )

    if not user:

        return {
            "logged_in": False
        }

    return {
        "logged_in": True,
        "user": {
            "id": user[0],
            "name": user[1],
            "email": user[2],
            "role": user[3]
        }
    }


# =========================================================
# LOGOUT
# =========================================================

@app.post("/api/logout")
def logout(
    response: Response,
    session: str | None = Cookie(default=None)
):

    if session:

        token_hash = hashlib.sha256(
            session.encode("utf-8")
        ).hexdigest()

        delete_session(
            token_hash
        )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/"
    )

    return {
        "success": True
    }


# =========================================================
# ALL BUSINESSES
# =========================================================

@app.get("/api/businesses")
def businesses():

    rows = get_businesses()

    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "address": row[5],
            "offer": row[6],
            "owner_id": row[7]
        }
        for row in rows
    ]


# =========================================================
# BUSINESS BY ID
# =========================================================

@app.get("/api/businesses/{business_id}")
def business_detail(
    business_id: int
):

    row = get_business_by_id(
        business_id
    )

    if not row:

        raise HTTPException(
            status_code=404,
            detail="Business not found."
        )

    return {
        "id": row[0],
        "name": row[1],
        "category": row[2],
        "latitude": row[3],
        "longitude": row[4],
        "address": row[5],
        "offer": row[6],
        "owner_id": row[7]
    }


# =========================================================
# ONE-TIME BUSINESS MIGRATION
# =========================================================

@app.post("/api/admin/migrate-businesses")
async def migrate_businesses(
    request: Request
):

    migration_secret = os.environ.get(
        "BUSINESS_MIGRATION_SECRET"
    )

    provided_secret = request.headers.get(
        "X-Migration-Secret"
    )

    if (
        not migration_secret
        or not provided_secret
        or not hmac.compare_digest(
            provided_secret,
            migration_secret
        )
    ):

        raise HTTPException(
            status_code=404,
            detail="Not found."
        )

    content_length = request.headers.get(
        "content-length"
    )

    if content_length:

        try:

            if int(content_length) > 1_000_000:

                raise HTTPException(
                    status_code=413,
                    detail="Migration payload too large."
                )

        except ValueError:

            raise HTTPException(
                status_code=400,
                detail="Invalid content length."
            )

    try:

        body = await request.json()

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload."
        )

    businesses_data = body.get(
        "businesses"
    )

    if not isinstance(
        businesses_data,
        list
    ):

        raise HTTPException(
            status_code=400,
            detail="Businesses list is required."
        )

    if len(businesses_data) > 500:

        raise HTTPException(
            status_code=400,
            detail="Too many businesses."
        )

    cleaned = []

    for item in businesses_data:

        if not isinstance(
            item,
            dict
        ):
            continue

        name = str(
            item.get("name", "")
        ).strip()

        category = str(
            item.get("category", "shop")
        ).strip().lower()

        address = str(
            item.get("address", "")
        ).strip()

        offer_value = item.get(
            "offer"
        )

        if offer_value is None:

            offer = ""

        else:

            offer = str(
                offer_value
            ).strip()[:500]

        try:

            latitude = float(
                item.get("latitude")
            )

            longitude = float(
                item.get("longitude")
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        if not name:
            continue

        if not (
            -90 <= latitude <= 90
        ):
            continue

        if not (
            -180 <= longitude <= 180
        ):
            continue

        if category not in (
            "cafe",
            "restaurant",
            "shop"
        ):

            category = "shop"

        cleaned.append(
            (
                name,
                category,
                latitude,
                longitude,
                address,
                offer,
                None
            )
        )

    if not cleaned:

        raise HTTPException(
            status_code=400,
            detail="No valid businesses found."
        )

    added = add_businesses(
        cleaned
    )

    print(
        f"BUSINESS MIGRATION | "
        f"received={len(businesses_data)} | "
        f"valid={len(cleaned)} | "
        f"added={added}"
    )

    return {
        "success": True,
        "received": len(businesses_data),
        "valid": len(cleaned),
        "added": added
    }


# =========================================================
# NEARBY BUSINESSES
# =========================================================

@app.get("/api/nearby")
def nearby(
    lat: float,
    lng: float
):

    if not -90 <= lat <= 90:

        raise HTTPException(
            status_code=400,
            detail="Invalid latitude."
        )

    if not -180 <= lng <= 180:

        raise HTTPException(
            status_code=400,
            detail="Invalid longitude."
        )

    # Always refresh Google Places results for this user's coordinates.
    # Returning cached rows early caused sparse/stale nearby results.

    if not GOOGLE_PLACES_API_KEY:

        raise HTTPException(
            status_code=500,
            detail="Google Places API key is not configured."
        )

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchNearby"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.location,"
            "places.types"
        )
    }

    payload = {
        "includedTypes": [
            "cafe",
            "restaurant",
            "store"
        ],
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": 30000.0
            }
        }
    }

    found = []
    seen = set()

    try:

        result = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        if not result.ok:

            safe_error = result.text[:1000]

            print(
                f"GOOGLE PLACES ERROR | "
                f"status={result.status_code} | "
                f"response={safe_error}"
            )

            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Google Places API request failed.",
                    "google_status": result.status_code
                }
            )

        data = result.json()

        places = data.get(
            "places",
            []
        )

        print(
            f"GOOGLE PLACES SUCCESS | "
            f"results={len(places)}"
        )

    except HTTPException:

        raise

    except requests.RequestException as error:

        print(
            f"GOOGLE PLACES REQUEST ERROR | "
            f"error={error}"
        )

        raise HTTPException(
            status_code=502,
            detail="Google Places request failed."
        )

    except ValueError:

        print(
            "GOOGLE PLACES JSON ERROR"
        )

        raise HTTPException(
            status_code=502,
            detail="Google returned an invalid response."
        )

    for place in places:

        place_id = place.get(
            "id"
        )

        if not place_id:
            continue

        if place_id in seen:
            continue

        seen.add(
            place_id
        )

        display_name = (
            place.get("displayName")
            or {}
        )

        name = display_name.get(
            "text",
            "Unnamed Business"
        )

        location = (
            place.get("location")
            or {}
        )

        latitude = location.get(
            "latitude"
        )

        longitude = location.get(
            "longitude"
        )

        address = place.get(
            "formattedAddress",
            ""
        )

        if (
            latitude is None
            or longitude is None
        ):
            continue

        google_types = place.get(
            "types",
            []
        )

        if "cafe" in google_types:

            category = "cafe"

        elif "restaurant" in google_types:

            category = "restaurant"

        elif "store" in google_types:

            category = "shop"

        else:

            category = "shop"

        found.append(
            (
                name,
                category,
                latitude,
                longitude,
                address,
                "",
                None
            )
        )

    print(
        f"NEARBY GOOGLE RESULTS | "
        f"found={len(found)}"
    )

    if found:

        added = add_businesses(
            found
        )

        print(
            f"NEARBY DATABASE SAVE | "
            f"added={added}"
        )

    nearby_rows = get_nearby_businesses(
        lat,
        lng,
        radius_km=30.0
    )

    print(
        f"NEARBY FINAL | "
        f"results={len(nearby_rows)}"
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "address": row[5],
            "offer": row[6],
            "owner_id": row[7],
            "distance_km": round(
                distance_km,
                2
            )
        }
        for row, distance_km in nearby_rows
    ]


# =========================================================
# LOAD BUSINESSES
# =========================================================

@app.post("/api/admin/load-businesses")
def load_businesses(request: Request):

    expected_secret = os.environ.get("BUSINESS_MIGRATION_SECRET", "")
    provided_secret = request.headers.get("X-Migration-Secret", "")
    if not expected_secret or not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
        raise HTTPException(status_code=404, detail="Not found.")

    if not GOOGLE_PLACES_API_KEY:

        raise HTTPException(
            status_code=500,
            detail="Google Places API key is not configured."
        )

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchText"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.location"
        )
    }

    queries = [
        "cafes in Huzurganj Madhya Pradesh",
        "restaurants in Huzurganj Madhya Pradesh",
        "shops in Huzurganj Madhya Pradesh"
    ]

    found = []

    for query in queries:

        payload = {
            "textQuery": query,
            "maxResultCount": 20
        }

        try:

            result = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=15
            )

            if not result.ok:
                continue

            places = result.json().get(
                "places",
                []
            )

        except requests.RequestException:

            continue

        for place in places:

            display_name = (
                place.get("displayName")
                or {}
            )

            location = (
                place.get("location")
                or {}
            )

            name = display_name.get(
                "text",
                "Unnamed Business"
            )

            latitude = location.get(
                "latitude"
            )

            longitude = location.get(
                "longitude"
            )

            address = place.get(
                "formattedAddress",
                ""
            )

            if (
                latitude is None
                or longitude is None
            ):
                continue

            category = "shop"

            query_lower = query.lower()

            if "cafe" in query_lower:

                category = "cafe"

            elif "restaurant" in query_lower:

                category = "restaurant"

            found.append(
                (
                    name,
                    category,
                    latitude,
                    longitude,
                    address,
                    "",
                    None
                )
            )

    added = add_businesses(
        found
    )

    return {
        "success": True,
        "added": added
    }


# =========================================================
# FOLLOW / UNFOLLOW
# =========================================================

@app.post("/api/businesses/{business_id}/follow")
def toggle_follow(
    business_id: int,
    session: str | None = Cookie(default=None)
):

    user = require_login(
        session
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM businesses WHERE id=?",
        (business_id,)
    )

    business = cursor.fetchone()

    conn.close()

    if not business:

        raise HTTPException(
            status_code=404,
            detail="Business not found."
        )

    user_id = user[0]

    if is_following(
        user_id,
        business_id
    ):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM follows
            WHERE user_id=?
            AND business_id=?
            """,
            (
                user_id,
                business_id
            )
        )

        conn.commit()
        conn.close()

        return {
            "following": False
        }

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO follows
        (
            user_id,
            business_id
        )
        VALUES (?,?)
        """,
        (
            user_id,
            business_id
        )
    )

    conn.commit()
    conn.close()

    return {
        "following": True
    }


# =========================================================
# CHECK FOLLOW
# =========================================================

@app.get("/api/businesses/{business_id}/follow")
def check_follow(
    business_id: int,
    session: str | None = Cookie(default=None)
):

    user = get_current_user(
        session
    )

    if not user:

        return {
            "following": False
        }

    return {
        "following": is_following(
            user[0],
            business_id
        )
    }


# =========================================================
# FOLLOWING
# =========================================================

@app.get("/api/following")
def following(
    session: str | None = Cookie(default=None)
):

    user = require_login(
        session
    )

    rows = get_followed_businesses(
        user[0]
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "address": row[5],
            "offer": row[6],
            "owner_id": row[7]
        }
        for row in rows
    ]



# =========================================================
# OWNER BUSINESS CLAIM REQUESTS
# =========================================================

@app.post("/api/owner/business-claims")
def submit_business_claim(
    business_id: int = Form(...),
    note: str = Form(""),
    session: str | None = Cookie(default=None)
):
    owner = require_owner(session)
    note = note.strip()
    if len(note) > 1000:
        raise HTTPException(status_code=400, detail="Note must be 1000 characters or fewer.")

    business = get_business_by_id(business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")
    if business[7] is not None:
        raise HTTPException(status_code=409, detail="This business is already assigned to an owner.")

    try:
        claim_id = create_business_claim_request(
            business_id, owner[0], note, int(time.time())
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A claim request already exists for this business.")

    return {
        "success": True,
        "claim_id": claim_id,
        "status": "pending",
        "message": "Request submitted. Ownership must be verified before access is granted."
    }


@app.get("/api/owner/business-claims")
def owner_business_claims(session: str | None = Cookie(default=None)):
    owner = require_owner(session)
    rows = get_business_claim_requests(owner[0])
    return [
        {
            "id": row[0],
            "business_id": row[1],
            "business_name": row[2],
            "address": row[3],
            "note": row[4],
            "status": row[5],
            "created_at": row[6]
        }
        for row in rows
    ]


@app.get("/api/admin/business-claims")
def admin_list_business_claims(request: Request):
    expected_secret = os.environ.get("BUSINESS_MIGRATION_SECRET", "")
    provided_secret = request.headers.get("X-Migration-Secret", "")
    if (
        not expected_secret
        or not provided_secret
        or not hmac.compare_digest(provided_secret, expected_secret)
    ):
        raise HTTPException(status_code=404, detail="Not found.")

    rows = get_pending_business_claim_requests()
    return [
        {
            "claim_id": row[0],
            "business_id": row[1],
            "business_name": row[2],
            "business_address": row[3],
            "owner_id": row[4],
            "owner_name": row[5],
            "owner_email": row[6],
            "verification_note": row[7],
            "created_at": row[8]
        }
        for row in rows
    ]


@app.post("/api/admin/business-claims/{claim_id}/review")
async def admin_review_business_claim(claim_id: int, request: Request):
    expected_secret = os.environ.get("BUSINESS_MIGRATION_SECRET", "")
    provided_secret = request.headers.get("X-Migration-Secret", "")
    if (
        not expected_secret
        or not provided_secret
        or not hmac.compare_digest(provided_secret, expected_secret)
    ):
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    status = payload.get("status") if isinstance(payload, dict) else None
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be approved or rejected.")

    result = review_business_claim_request(
        claim_id, status, int(time.time()), "manual-admin-review"
    )
    if result["result"] == "not_pending":
        raise HTTPException(status_code=404, detail="Pending claim request not found.")
    if result["result"] == "already_claimed":
        raise HTTPException(status_code=409, detail="Business has already been assigned to an owner.")

    return {"success": True, **result}


# =========================================================
# OWNER SIGNUP
# =========================================================

@app.post("/api/owner/signup")
def owner_signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):

    name = name.strip()
    email = email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address."
        )

    if not name:

        raise HTTPException(
            status_code=400,
            detail="Name is required."
        )

    if not email:

        raise HTTPException(
            status_code=400,
            detail="Email is required."
        )

    if len(password) < 8:

        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters."
        )

    existing_owner = get_user_by_email_and_role(
        email,
        "owner"
    )

    if existing_owner:

        raise HTTPException(
            status_code=400,
            detail="Owner account already exists for this email."
        )

    password_hash = hash_password(
        password
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password_hash,
                role
            )
            VALUES (?, ?, ?, 'owner')
            """,
            (
                name,
                email,
                password_hash
            )
        )

        owner_id = cursor.lastrowid

        conn.commit()

    except Exception:

        conn.rollback()
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Could not create owner account."
        )

    conn.close()

    return {
        "success": True,
        "owner_id": owner_id,
        "role": "owner"
    }


# =========================================================
# OWNER LOGIN
# =========================================================

@app.post("/api/owner/login")
def owner_login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...)
):

    email = email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address."
        )

    user = get_user_by_email_and_role(
        email,
        "owner"
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid owner email or password."
        )

    if not verify_password(
        password,
        user[3]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid owner email or password."
        )

    token = create_secure_session(
        user[0]
    )

    set_session_cookie(
        response,
        token
    )

    return {
        "success": True,
        "user": {
            "id": user[0],
            "name": user[1],
            "email": user[2],
            "role": user[4]
        }
    }


# =========================================================
# OWNER BUSINESSES
# =========================================================

@app.get("/api/owner/businesses")
def owner_businesses(
    session: str | None = Cookie(default=None)
):

    owner = require_owner(
        session
    )

    rows = get_owner_businesses(
        owner[0]
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "address": row[5],
            "offer": row[6],
            "owner_id": row[7]
        }
        for row in rows
    ]


# =========================================================
# OWNER UPDATE OFFER
# =========================================================

@app.post("/api/businesses/{business_id}/offer")
def update_offer(
    business_id: int,
    offer: str = Form(""),
    session: str | None = Cookie(default=None)
):

    owner = require_owner(
        session
    )

    offer = offer.strip()

    if len(offer) > 500:

        raise HTTPException(
            status_code=400,
            detail="Offer is too long."
        )

    row = get_business_by_id(
        business_id
    )

    if not row:

        raise HTTPException(
            status_code=404,
            detail="Business not found."
        )

    if row[7] != owner[0]:

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to edit this business."
        )

    updated = update_business_offer(
        business_id,
        owner[0],
        offer
    )

    if updated == 0:

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to edit this business."
        )

    return {
        "success": True
    }