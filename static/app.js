from fastapi import FastAPI, HTTPException, Form, Response, Cookie
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import requests
import hashlib
import secrets
import math

from database import (
    init_db,
    get_businesses,
    add_businesses,
    is_following,
    get_followed_businesses,
    get_connection,
    get_user_by_email,
    get_user_by_id,
    get_owner_businesses,
    get_business_by_id,
    assign_business_to_owner,
    update_business_offer
)

from config import GOOGLE_PLACES_API_KEY


# =========================================================
# APP
# =========================================================

app = FastAPI()


# =========================================================
# STATIC FILES
# =========================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


# =========================================================
# DATABASE
# =========================================================

init_db()


# =========================================================
# PASSWORD HASHING
# =========================================================

def hash_password(password: str):

    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        100000
    ).hex()

    return f"{salt}:{password_hash}"


def verify_password(
    password: str,
    stored_password: str
):

    try:

        salt, stored_hash = stored_password.split(
            ":",
            1
        )

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            100000
        ).hex()

        return secrets.compare_digest(
            password_hash,
            stored_hash
        )

    except (ValueError, AttributeError):

        return False


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return FileResponse(
        "static/index.html"
    )


# =========================================================
# SIGNUP
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
            detail="Name is required"
        )

    if not email:

        raise HTTPException(
            status_code=400,
            detail="Email is required"
        )

    if len(password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters"
        )

    if get_user_by_email(email):

        raise HTTPException(
            status_code=400,
            detail="Email already registered"
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

    except Exception as error:

        conn.rollback()
        conn.close()

        print("Signup error:", error)

        raise HTTPException(
            status_code=400,
            detail="Unable to create account"
        )

    conn.close()

    return {
        "success": True,
        "message": "Account created",
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
            detail="Invalid email or password"
        )

    user_id = user[0]
    name = user[1]
    user_email = user[2]
    stored_password = user[3]

    if not verify_password(
        password,
        stored_password
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    response.set_cookie(
        key="user_id",
        value=str(user_id),
        httponly=True,
        samesite="lax",
        path="/"
    )

    return {
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user_id,
            "name": name,
            "email": user_email,
            "role": user[4]
        }
    }


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/api/me")
def current_user(
    user_id: str | None = Cookie(default=None)
):

    if not user_id:

        return {
            "logged_in": False
        }

    try:

        user_id_int = int(user_id)

    except ValueError:

        return {
            "logged_in": False
        }

    user = get_user_by_id(user_id_int)

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
        key="user_id",
        path="/"
    )

    response.delete_cookie(
        key="owner_id",
        path="/"
    )

    return {
        "success": True,
        "message": "Logged out"
    }


# =========================================================
# ALL BUSINESSES
# =========================================================

@app.get("/api/businesses")
def businesses():

    data = get_businesses()

    return [
        {
            "id": business[0],
            "name": business[1],
            "category": business[2],
            "latitude": business[3],
            "longitude": business[4],
            "address": business[5],
            "offer": business[6],
            "owner_id": business[7]
        }
        for business in data
    ]


# =========================================================
# DISTANCE CALCULATION
# =========================================================

def calculate_distance_km(
    lat1,
    lng1,
    lat2,
    lng2
):

    if (
        lat1 is None
        or lng1 is None
        or lat2 is None
        or lng2 is None
    ):
        return None

    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lng = math.radians(
        lng2 - lng1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(delta_lng / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius_km * c


# =========================================================
# NEARBY BUSINESSES
# =========================================================

@app.get("/api/nearby")
def nearby(
    lat: float | None = None,
    lng: float | None = None
):

    if lat is None or lng is None:

        raise HTTPException(
            status_code=400,
            detail="Location coordinates are required"
        )

    if not (
        -90 <= lat <= 90
        and -180 <= lng <= 180
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid location coordinates"
        )


    # =====================================================
    # GOOGLE PLACES NEARBY SEARCH
    # =====================================================

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchNearby"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.location,"
            "places.types"
        )
    }


    body = {

        "includedTypes": [
            "cafe",
            "restaurant",
            "coffee_shop",
            "bakery",
            "clothing_store",
            "grocery_store",
            "beauty_salon",
            "hair_salon",
            "pharmacy",
            "gym",
            "book_store"
        ],

        "maxResultCount": 20,

        "rankPreference": "DISTANCE",

        "locationRestriction": {

            "circle": {

                "center": {
                    "latitude": lat,
                    "longitude": lng
                },

                "radius": 5000.0
            }
        }
    }


    try:

        google_response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=20
        )

    except requests.RequestException as error:

        print(
            "Google Nearby Search error:",
            error
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to contact Google Places"
        )


    if google_response.status_code != 200:

        print(
            "Google Nearby Search failed:",
            google_response.status_code,
            google_response.text
        )

        raise HTTPException(
            status_code=502,
            detail="Google Places search failed"
        )


    google_data = google_response.json()

    places = google_data.get(
        "places",
        []
    )


    # =====================================================
    # SAVE GOOGLE BUSINESSES TO DATABASE
    # =====================================================

    businesses_to_save = []


    for place in places:

        display_name = place.get(
            "displayName",
            {}
        )

        name = display_name.get(
            "text",
            "Unknown Business"
        )


        address = place.get(
            "formattedAddress",
            ""
        )


        location = place.get(
            "location",
            {}
        )


        business_latitude = location.get(
            "latitude"
        )

        business_longitude = location.get(
            "longitude"
        )


        place_types = place.get(
            "types",
            []
        )


        category = "business"

        if "cafe" in place_types:
            category = "cafe"

        elif "restaurant" in place_types:
            category = "restaurant"

        elif "coffee_shop" in place_types:
            category = "cafe"

        elif "bakery" in place_types:
            category = "bakery"

        elif (
            "clothing_store"
            in place_types
        ):
            category = "shop"

        elif (
            "grocery_store"
            in place_types
        ):
            category = "shop"

        elif (
            "beauty_salon"
            in place_types
        ):
            category = "salon"

        elif (
            "hair_salon"
            in place_types
        ):
            category = "salon"

        elif "gym" in place_types:
            category = "gym"

        elif "book_store" in place_types:
            category = "shop"


        if (
            business_latitude is None
            or business_longitude is None
        ):
            continue


        businesses_to_save.append(
            (
                name,
                category,
                business_latitude,
                business_longitude,
                address,
                None,
                None
            )
        )


    if businesses_to_save:

        add_businesses(
            businesses_to_save
        )


    # =====================================================
    # RETURN NEARBY BUSINESSES
    # =====================================================

    nearby_businesses = []

    for business in businesses_to_save:

        distance = calculate_distance_km(
            lat,
            lng,
            business[2],
            business[3]
        )

        nearby_businesses.append({

            "id": None,

            "name": business[0],

            "category": business[1],

            "latitude": business[2],

            "longitude": business[3],

            "address": business[4],

            "offer": business[5],

            "owner_id": business[6],

            "distance_km": (
                round(distance, 2)
                if distance is not None
                else None
            )
        })


    # =====================================================
    # GET DATABASE IDS + EXISTING OFFERS
    # =====================================================

    all_database_businesses = get_businesses()


    for item in nearby_businesses:

        for database_business in all_database_businesses:

            same_name = (
                database_business[1]
                == item["name"]
            )

            same_address = (
                database_business[5]
                == item["address"]
            )

            if same_name and same_address:

                item["id"] = database_business[0]

                item["offer"] = (
                    database_business[6]
                )

                item["owner_id"] = (
                    database_business[7]
                )

                break


    nearby_businesses.sort(
        key=lambda item:
            item["distance_km"]
            if item["distance_km"] is not None
            else 999999
    )


    return nearby_businesses


# =========================================================
# LOAD BUSINESSES FROM GOOGLE PLACES
# =========================================================

@app.get("/api/load-businesses")
def load_businesses():

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchText"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.location"
        )
    }

    searches = [
        (
            "cafe",
            "cafes near Huzurganj, Madhya Pradesh"
        ),
        (
            "restaurant",
            "restaurants near Huzurganj, Madhya Pradesh"
        ),
        (
            "shop",
            "shops near Huzurganj, Madhya Pradesh"
        )
    ]

    total_found = 0
    total_added = 0

    for category, text_query in searches:

        data = {
            "textQuery": text_query
        }

        try:

            google_response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=15
            )

        except requests.RequestException as error:

            print(
                f"Google Places error for {category}:",
                error
            )

            continue

        if google_response.status_code != 200:

            print(
                f"Google Places failed for {category}:",
                google_response.status_code,
                google_response.text
            )

            continue

        places = google_response.json().get(
            "places",
            []
        )

        total_found += len(places)

        businesses_to_save = []

        for place in places:

            name = (
                place.get(
                    "displayName",
                    {}
                )
                .get(
                    "text",
                    "Unknown"
                )
            )

            address = place.get(
                "formattedAddress",
                ""
            )

            location = place.get(
                "location",
                {}
            )

            latitude = location.get(
                "latitude"
            )

            longitude = location.get(
                "longitude"
            )

            businesses_to_save.append(
                (
                    name,
                    category,
                    latitude,
                    longitude,
                    address,
                    None,
                    None
                )
            )

        if businesses_to_save:

            added = add_businesses(
                businesses_to_save
            )

            total_added += added


    return {
        "success": True,
        "found": total_found,
        "added": total_added,
        "message": "Businesses loaded successfully"
    }


# =========================================================
# FOLLOW / UNFOLLOW
# =========================================================

@app.post(
    "/api/businesses/{business_id}/follow"
)
def follow_business(
    business_id: int,
    user_id: str | None = Cookie(default=None)
):

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Please login first"
        )

    try:

        user_id_int = int(user_id)

    except ValueError:

        raise HTTPException(
            status_code=401,
            detail="Invalid session"
        )

    user = get_user_by_id(
        user_id_int
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid session"
        )

    business = get_business_by_id(
        business_id
    )

    if not business:

        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM follows
        WHERE user_id = ?
        AND business_id = ?
        """,
        (
            user_id_int,
            business_id
        )
    )

    existing = cursor.fetchone()

    if existing:

        cursor.execute(
            """
            DELETE FROM follows
            WHERE user_id = ?
            AND business_id = ?
            """,
            (
                user_id_int,
                business_id
            )
        )

        following = False

    else:

        cursor.execute(
            """
            INSERT INTO follows
            (
                user_id,
                business_id
            )
            VALUES (?, ?)
            """,
            (
                user_id_int,
                business_id
            )
        )

        following = True

    conn.commit()
    conn.close()

    return {
        "success": True,
        "following": following
    }


# =========================================================
# CHECK FOLLOW STATUS
# =========================================================

@app.get(
    "/api/businesses/{business_id}/follow"
)
def check_following(
    business_id: int,
    user_id: str | None = Cookie(default=None)
):

    if not user_id:

        return {
            "following": False
        }

    try:

        user_id_int = int(user_id)

    except ValueError:

        return {
            "following": False
        }

    return {
        "following": is_following(
            user_id_int,
            business_id
        )
    }


# =========================================================
# FOLLOWED BUSINESSES
# =========================================================

@app.get("/api/following")
def following(
    user_id: str | None = Cookie(default=None)
):

    if not user_id:
        return []

    try:

        user_id_int = int(user_id)

    except ValueError:

        return []

    user = get_user_by_id(
        user_id_int
    )

    if not user:
        return []

    data = get_followed_businesses(
        user_id_int
    )

    return [
        {
            "id": business[0],
            "name": business[1],
            "category": business[2],
            "latitude": business[3],
            "longitude": business[4],
            "address": business[5],
            "offer": business[6],
            "owner_id": business[7]
        }
        for business in data
    ]


# =========================================================
# GET BUSINESS BY ID
# =========================================================

@app.get(
    "/api/businesses/{business_id}"
)
def get_business(
    business_id: int
):

    business = get_business_by_id(
        business_id
    )

    if not business:

        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    return {
        "id": business[0],
        "name": business[1],
        "category": business[2],
        "latitude": business[3],
        "longitude": business[4],
        "address": business[5],
        "offer": business[6],
        "owner_id": business[7]
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

    user = get_user_by_email(email)

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid owner email or password"
        )

    user_id = user[0]
    name = user[1]
    user_email = user[2]
    password_hash = user[3]
    role = user[4]

    if role != "owner":

        raise HTTPException(
            status_code=403,
            detail="This account is not a business owner account"
        )

    if not verify_password(
        password,
        password_hash
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid owner email or password"
        )

    response.delete_cookie(
        key="user_id",
        path="/"
    )

    response.set_cookie(
        key="owner_id",
        value=str(user_id),
        httponly=True,
        samesite="lax",
        path="/"
    )

    return {
        "success": True,
        "message": "Owner login successful",
        "owner": {
            "id": user_id,
            "name": name,
            "email": user_email,
            "role": role
        }
    }


# =========================================================
# CURRENT OWNER
# =========================================================

@app.get("/api/owner/me")
def current_owner(
    owner_id: str | None = Cookie(default=None)
):

    if not owner_id:

        return {
            "logged_in": False
        }

    try:

        owner_id_int = int(owner_id)

    except ValueError:

        return {
            "logged_in": False
        }

    owner = get_user_by_id(
        owner_id_int
    )

    if not owner:

        return {
            "logged_in": False
        }

    if owner[3] != "owner":

        return {
            "logged_in": False
        }

    return {
        "logged_in": True,
        "owner": {
            "id": owner[0],
            "name": owner[1],
            "email": owner[2],
            "role": owner[3]
        }
    }


# =========================================================
# OWNER BUSINESSES
# =========================================================

@app.get("/api/owner/businesses")
def owner_businesses(
    owner_id: str | None = Cookie(default=None)
):

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Owner login required"
        )

    try:

        owner_id_int = int(owner_id)

    except ValueError:

        raise HTTPException(
            status_code=401,
            detail="Invalid owner session"
        )

    owner = get_user_by_id(
        owner_id_int
    )

    if not owner or owner[3] != "owner":

        raise HTTPException(
            status_code=403,
            detail="Owner access required"
        )

    data = get_owner_businesses(
        owner_id_int
    )

    return [
        {
            "id": business[0],
            "name": business[1],
            "category": business[2],
            "latitude": business[3],
            "longitude": business[4],
            "address": business[5],
            "offer": business[6],
            "owner_id": business[7]
        }
        for business in data
    ]


# =========================================================
# UPDATE BUSINESS OFFER
# =========================================================

@app.post(
    "/api/businesses/{business_id}/offer"
)
def update_offer(
    business_id: int,
    offer: str = Form(...),
    owner_id: str | None = Cookie(default=None)
):

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Owner login required"
        )

    try:

        owner_id_int = int(owner_id)

    except ValueError:

        raise HTTPException(
            status_code=401,
            detail="Invalid owner session"
        )

    owner = get_user_by_id(
        owner_id_int
    )

    if not owner or owner[3] != "owner":

        raise HTTPException(
            status_code=403,
            detail="Owner access required"
        )

    offer = offer.strip()

    if not offer:

        raise HTTPException(
            status_code=400,
            detail="Offer cannot be empty"
        )

    business = get_business_by_id(
        business_id
    )

    if not business:

        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    if business[7] != owner_id_int:

        raise HTTPException(
            status_code=403,
            detail="You do not own this business"
        )

    updated = update_business_offer(
        business_id,
        owner_id_int,
        offer
    )

    if not updated:

        raise HTTPException(
            status_code=400,
            detail="Offer could not be updated"
        )

    return {
        "success": True,
        "business_id": business_id,
        "offer": offer
    }


# =========================================================
# ASSIGN BUSINESS TO OWNER
# =========================================================

@app.post(
    "/api/owner/businesses/{business_id}/assign"
)
def assign_owner_business(
    business_id: int,
    owner_id: str | None = Cookie(default=None)
):

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Owner login required"
        )

    try:

        owner_id_int = int(owner_id)

    except ValueError:

        raise HTTPException(
            status_code=401,
            detail="Invalid owner session"
        )

    owner = get_user_by_id(
        owner_id_int
    )

    if not owner or owner[3] != "owner":

        raise HTTPException(
            status_code=403,
            detail="Owner access required"
        )

    business = get_business_by_id(
        business_id
    )

    if not business:

        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    if business[7] is not None:

        raise HTTPException(
            status_code=400,
            detail="Business already has an owner"
        )

    updated = assign_business_to_owner(
        business_id,
        owner_id_int
    )

    if not updated:

        raise HTTPException(
            status_code=400,
            detail="Business could not be assigned"
        )

    return {
        "success": True,
        "business_id": business_id,
        "owner_id": owner_id_int
    }