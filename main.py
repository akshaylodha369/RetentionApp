
from fastapi import FastAPI, HTTPException, Form, Response, Cookie
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import requests
import hashlib
import secrets

from database import (
    init_db,
    get_businesses,
    add_businesses,
    get_nearby_businesses,
    is_following,
    get_followed_businesses,
    get_connection
)

from config import GOOGLE_PLACES_API_KEY


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

        salt, stored_hash = stored_password.split(":")

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

    except ValueError:

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

    password_hash = hash_password(
        password
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (name, email, password_hash)
            VALUES (?, ?, ?)
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
            detail="Email already registered"
        )

    conn.close()

    return {
        "success": True,
        "message": "Account created",
        "user_id": user_id
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/api/login")
def login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...)
):

    email = email.strip().lower()

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
        """,
        (email,)
    )

    user = cursor.fetchone()

    conn.close()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    user_id = user[0]
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
        samesite="lax"
    )

    return {
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user_id,
            "name": user[1],
            "email": user[2],
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

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            email,
            role
        FROM users
        WHERE id = ?
        """,
        (user_id_int,)
    )

    user = cursor.fetchone()

    conn.close()

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
        key="user_id"
    )

    return {
        "success": True
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
# GOOGLE PLACES SEARCH
# =========================================================

def search_nearby_google_places(
    latitude,
    longitude,
    category
):

    print("----------------------------------------")
    print("GOOGLE PLACES SEARCH")
    print("Category:", category)
    print("Latitude:", latitude)
    print("Longitude:", longitude)
    print(
        "GOOGLE_PLACES_API_KEY EXISTS:",
        bool(GOOGLE_PLACES_API_KEY)
    )


    if not GOOGLE_PLACES_API_KEY:

        print(
            "ERROR: GOOGLE_PLACES_API_KEY IS MISSING"
        )

        return []


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
            category
        ],

        "maxResultCount": 20,

        "rankPreference": "DISTANCE",

        "locationRestriction": {

            "circle": {

                "center": {

                    "latitude": latitude,
                    "longitude": longitude

                },

                "radius": 5000.0
            }
        }
    }


    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

    except requests.RequestException as error:

        print(
            "GOOGLE REQUEST EXCEPTION:",
            error
        )

        return []


    print(
        "Google HTTP status:",
        response.status_code
    )


    if response.status_code != 200:

        print(
            "GOOGLE API ERROR:"
        )

        print(
            response.text
        )

        return []


    try:

        data = response.json()

    except ValueError:

        print(
            "GOOGLE RESPONSE IS NOT VALID JSON"
        )

        print(
            response.text
        )

        return []


    places = data.get(
        "places",
        []
    )


    print(
        "Google results:",
        len(places)
    )


    if not places:

        print(
            "Google returned ZERO businesses"
        )


    return places


# =========================================================
# NEARBY BUSINESSES
# =========================================================

@app.get("/api/nearby")
def nearby(
    lat: float | None = None,
    lng: float | None = None
):

    print("")
    print("========================================")
    print("NEARBY SEARCH START")
    print("========================================")

    print(
        "GOOGLE_PLACES_API_KEY EXISTS:",
        bool(GOOGLE_PLACES_API_KEY)
    )

    print(
        "User latitude:",
        lat
    )

    print(
        "User longitude:",
        lng
    )


    # -----------------------------------------------------
    # VALIDATE LOCATION
    # -----------------------------------------------------

    if lat is None or lng is None:

        raise HTTPException(
            status_code=400,
            detail="Latitude and longitude are required"
        )


    if not (-90 <= lat <= 90):

        raise HTTPException(
            status_code=400,
            detail="Invalid latitude"
        )


    if not (-180 <= lng <= 180):

        raise HTTPException(
            status_code=400,
            detail="Invalid longitude"
        )


    # -----------------------------------------------------
    # GOOGLE CATEGORIES
    # -----------------------------------------------------

    google_categories = [
        "cafe",
        "restaurant",
        "store"
    ]


    google_businesses = []

    seen_places = set()


    # -----------------------------------------------------
    # SEARCH GOOGLE
    # -----------------------------------------------------

    for google_category in google_categories:

        places = search_nearby_google_places(
            lat,
            lng,
            google_category
        )


        for place in places:

            place_id = place.get(
                "id"
            )


            if place_id:

                if place_id in seen_places:

                    continue

                seen_places.add(
                    place_id
                )


            google_businesses.append(
                place
            )


    print(
        "TOTAL UNIQUE GOOGLE BUSINESSES:",
        len(google_businesses)
    )


    # -----------------------------------------------------
    # SAVE GOOGLE BUSINESSES
    # -----------------------------------------------------

    businesses_to_save = []


    for place in google_businesses:

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


        if (
            business_latitude is None
            or
            business_longitude is None
        ):

            continue


        types = place.get(
            "types",
            []
        )


        if "cafe" in types:

            category = "cafe"

        elif "restaurant" in types:

            category = "restaurant"

        else:

            category = "shop"


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


    added_count = 0


    if businesses_to_save:

        try:

            added_count = add_businesses(
                businesses_to_save
            )

        except Exception as error:

            print(
                "DATABASE SAVE ERROR:",
                error
            )


    print(
        "GOOGLE BUSINESSES ADDED:",
        added_count
    )


    # -----------------------------------------------------
    # GET BUSINESSES FROM DATABASE
    # -----------------------------------------------------

    try:

        nearby_data = get_nearby_businesses(
            lat,
            lng,
            radius_km=5.0
        )

    except Exception as error:

        print(
            "DATABASE NEARBY ERROR:",
            error
        )

        nearby_data = []


    print(
        "DATABASE BUSINESSES WITHIN 5 KM:",
        len(nearby_data)
    )


    # -----------------------------------------------------
    # BUILD RESPONSE
    # -----------------------------------------------------

    result = []


    for business, distance_km in nearby_data:

        result.append(
            {
                "id": business[0],
                "name": business[1],
                "category": business[2],
                "latitude": business[3],
                "longitude": business[4],
                "address": business[5],
                "offer": business[6],
                "owner_id": business[7],
                "distance_km": round(
                    distance_km,
                    2
                )
            }
        )


    print(
        "FINAL BUSINESSES RETURNED:",
        len(result)
    )

    print("========================================")
    print("NEARBY SEARCH END")
    print("========================================")
    print("")


    return result


# =========================================================
# LOAD BUSINESSES
# =========================================================

@app.get("/api/load-businesses")
def load_businesses():

    print(
        "========================================"
    )

    print(
        "LOAD BUSINESSES"
    )

    print(
        "GOOGLE_PLACES_API_KEY EXISTS:",
        bool(GOOGLE_PLACES_API_KEY)
    )


    if not GOOGLE_PLACES_API_KEY:

        raise HTTPException(
            status_code=500,
            detail="GOOGLE_PLACES_API_KEY is not configured"
        )


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

            response = requests.post(
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


        print(
            f"Google Text Search {category}:",
            response.status_code
        )


        if response.status_code != 200:

            print(
                response.text
            )

            continue


        try:

            places = response.json().get(
                "places",
                []
            )

        except ValueError:

            print(
                "Invalid JSON from Google"
            )

            continue


        total_found += len(
            places
        )


        businesses_to_save = []


        for place in places:

            name = place.get(
                "displayName",
                {}
            ).get(
                "text",
                "Unknown"
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


            if (
                latitude is None
                or
                longitude is None
            ):

                continue


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

            try:

                added = add_businesses(
                    businesses_to_save
                )

                total_added += added

            except Exception as error:

                print(
                    "Database error:",
                    error
                )


    print(
        "TOTAL FOUND:",
        total_found
    )

    print(
        "TOTAL ADDED:",
        total_added
    )


    return {
        "success": True,
        "found": total_found,
        "added": total_added,
        "message": (
            "Cafes, restaurants and shops "
            "loaded successfully"
        )
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
            (user_id, business_id)
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
# UPDATE BUSINESS OFFER
# =========================================================

@app.post(
    "/api/businesses/{business_id}/offer"
)
def update_offer(
    business_id: int,
    offer: str = Form(...)
):

    offer = offer.strip()


    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT id
        FROM businesses
        WHERE id = ?
        """,
        (business_id,)
    )


    business = cursor.fetchone()


    if not business:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )


    cursor.execute(
        """
        UPDATE businesses
        SET offer = ?
        WHERE id = ?
        """,
        (
            offer,
            business_id
        )
    )


    conn.commit()
    conn.close()


    return {
        "success": True,
        "business_id": business_id,
        "offer": offer
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
