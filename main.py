from fastapi import FastAPI, HTTPException, Form, Response, Cookie, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import hashlib
import hmac
import os
import secrets
import requests

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

init_db()


# =========================================================
# SECURITY / PASSWORDS
# =========================================================

PASSWORD_ITERATIONS = 100000

SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    secrets.token_hex(32)
)


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


def create_session(user_id):

    user_value = str(user_id)

    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        user_value.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return user_value + "." + signature


def get_current_user(session):

    if not session:
        return None

    try:
        user_value, signature = session.split(".", 1)
        uid = int(user_value)
    except Exception:
        return None

    expected_signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        user_value.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(
        signature,
        expected_signature
    ):
        return None

    return get_user_by_id(uid)


def require_login(session):

    user = get_current_user(session)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Please login first."
        )

    return user


def require_owner(session):

    user = require_login(session)

    if user[3] != "owner":
        raise HTTPException(
            status_code=403,
            detail="Owner access required."
        )

    return user


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

    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    existing_user = get_user_by_email(email)

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered."
        )

    password_hash = hash_password(password)

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

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Could not create account."
        )

    conn.close()

    return {
        "success": True,
        "user_id": user_id
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

    user = get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not verify_password(
        password,
        user[3]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    session = create_session(user[0])

    response.set_cookie(
        key="session",
        value=session,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30
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

    user = get_current_user(session)

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
def logout(response: Response):

    response.delete_cookie(
        "session"
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

    cached_rows = get_nearby_businesses(
        lat,
        lng,
        radius_km=3.0
    )

    if cached_rows:

        print(
            f"NEARBY CACHE HIT | "
            f"results={len(cached_rows)}"
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
            for row, distance_km in cached_rows
        ]

    print(
        "NEARBY CACHE MISS | "
        "No businesses found in database."
    )

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
                "radius": 3000.0
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

        place_id = place.get("id")

        if not place_id:
            continue

        if place_id in seen:
            continue

        seen.add(place_id)

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
        radius_km=3.0
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

@app.get("/api/load-businesses")
def load_businesses():

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

    user = require_login(session)

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


@app.get("/api/businesses/{business_id}/follow")
def check_follow(
    business_id: int,
    session: str | None = Cookie(default=None)
):

    user = get_current_user(session)

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

    user = require_login(session)

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

    if len(password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    if get_user_by_email(email):

        raise HTTPException(
            status_code=400,
            detail="Email already registered."
        )

    password_hash = hash_password(
        password
    )

    try:

        owner_id = create_owner(
            name,
            email,
            password_hash
        )

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Could not create owner account."
        )

    return {
        "success": True,
        "owner_id": owner_id
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

    user = get_user_by_email(
        email
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if user[4] != "owner":

        raise HTTPException(
            status_code=403,
            detail="This account is not an owner account."
        )

    if not verify_password(
        password,
        user[3]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    session = create_session(
        user[0]
    )

    response.set_cookie(
        key="session",
        value=session,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30
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
    offer: str = Form(...),
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

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE businesses
        SET offer=?
        WHERE id=?
        AND owner_id=?
        """,
        (
            offer,
            business_id,
            owner[0]
        )
    )

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    if updated == 0:

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to edit this business."
        )

    return {
        "success": True
    }