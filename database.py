import os
import sqlite3
import math


# Set DATABASE_PATH to a persistent disk path on Render, e.g. /var/data/retention.db.
# Local development keeps the database in the project root.
DB_NAME = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "retention.db"))


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    parent = os.path.dirname(DB_NAME)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_NAME, timeout=15)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    # =====================================================
    # USERS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer'
        )
    """)

    # =====================================================
    # BUSINESSES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            latitude REAL,
            longitude REAL,
            address TEXT,
            offer TEXT,
            owner_id INTEGER
        )
    """)

    # =====================================================
    # FOLLOWS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            business_id INTEGER NOT NULL,
            UNIQUE(user_id, business_id)
        )
    """)

    # =====================================================
    # SESSIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
        ON sessions(token_hash)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id
        ON sessions(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
        ON sessions(expires_at)
    """)

    # Owner claims are requests only. A business is assigned only after an
    # administrator manually verifies the claimant outside the app.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS business_claim_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at INTEGER NOT NULL,
            reviewed_at INTEGER,
            reviewed_by TEXT,
            UNIQUE(business_id),
            FOREIGN KEY(business_id) REFERENCES businesses(id),
            FOREIGN KEY(owner_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_claim_requests_status
        ON business_claim_requests(status, created_at)
    """)

    conn.commit()
    conn.close()


# =========================================================
# GET ALL BUSINESSES
# =========================================================

def get_businesses():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            category,
            latitude,
            longitude,
            address,
            offer,
            owner_id
        FROM businesses
    """)

    businesses = cursor.fetchall()

    conn.close()

    return businesses


# =========================================================
# ADD BUSINESSES
# =========================================================

def add_businesses(businesses):

    conn = get_connection()
    cursor = conn.cursor()

    added = 0

    for business in businesses:

        if len(business) < 7:
            continue

        name = business[0]
        category = business[1]
        latitude = business[2]
        longitude = business[3]
        address = business[4]
        offer = business[5]
        owner_id = business[6]

        cursor.execute("""
            SELECT id
            FROM businesses
            WHERE name = ?
            AND address = ?
        """, (
            name,
            address
        ))

        existing = cursor.fetchone()

        if existing:
            continue

        cursor.execute("""
            INSERT INTO businesses
            (
                name,
                category,
                latitude,
                longitude,
                address,
                offer,
                owner_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            category,
            latitude,
            longitude,
            address,
            offer,
            owner_id
        ))

        added += 1

    conn.commit()
    conn.close()

    return added


# =========================================================
# HAVERSINE DISTANCE
# =========================================================

def calculate_distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius_km = 6371.0

    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))

    delta_lat = math.radians(
        float(lat2) - float(lat1)
    )

    delta_lon = math.radians(
        float(lon2) - float(lon1)
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius_km * c


# =========================================================
# GET NEARBY BUSINESSES
# =========================================================

def get_nearby_businesses(
    latitude,
    longitude,
    radius_km=5.0
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            category,
            latitude,
            longitude,
            address,
            offer,
            owner_id
        FROM businesses
        WHERE latitude IS NOT NULL
        AND longitude IS NOT NULL
    """)

    businesses = cursor.fetchall()

    conn.close()

    nearby = []

    for business in businesses:

        business_latitude = business[3]
        business_longitude = business[4]

        try:

            distance_km = calculate_distance_km(
                latitude,
                longitude,
                business_latitude,
                business_longitude
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        if distance_km <= radius_km:

            nearby.append(
                (
                    business,
                    distance_km
                )
            )

    nearby.sort(
        key=lambda item: item[1]
    )

    return nearby


# =========================================================
# FOLLOW BUSINESS
# =========================================================

def follow_business(
    user_id,
    business_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO follows
        (
            user_id,
            business_id
        )
        VALUES (?, ?)
    """, (
        user_id,
        business_id
    ))

    conn.commit()
    conn.close()


# =========================================================
# UNFOLLOW BUSINESS
# =========================================================

def unfollow_business(
    user_id,
    business_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM follows
        WHERE user_id = ?
        AND business_id = ?
    """, (
        user_id,
        business_id
    ))

    conn.commit()
    conn.close()


# =========================================================
# CHECK FOLLOW STATUS
# =========================================================

def is_following(
    user_id,
    business_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM follows
        WHERE user_id = ?
        AND business_id = ?
    """, (
        user_id,
        business_id
    ))

    result = cursor.fetchone()

    conn.close()

    return result is not None


# =========================================================
# GET FOLLOWED BUSINESSES
# =========================================================

def get_followed_businesses(
    user_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            b.id,
            b.name,
            b.category,
            b.latitude,
            b.longitude,
            b.address,
            b.offer,
            b.owner_id
        FROM businesses b
        INNER JOIN follows f
            ON b.id = f.business_id
        WHERE f.user_id = ?
    """, (
        user_id,
    ))

    businesses = cursor.fetchall()

    conn.close()

    return businesses


# =========================================================
# GET USER BY EMAIL
# =========================================================

def get_user_by_email(
    email
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            password_hash,
            role
        FROM users
        WHERE email = ?
    """, (
        email,
    ))

    user = cursor.fetchone()

    conn.close()

    return user


# =========================================================
# GET USER BY ID
# =========================================================

def get_user_by_id(
    user_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            role
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    user = cursor.fetchone()

    conn.close()

    return user


# =========================================================
# CREATE OWNER
# =========================================================

def create_owner(
    name,
    email,
    password_hash
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users
        (
            name,
            email,
            password_hash,
            role
        )
        VALUES (?, ?, ?, 'owner')
    """, (
        name,
        email,
        password_hash
    ))

    owner_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return owner_id


# =========================================================
# GET OWNER BUSINESSES
# =========================================================

def get_owner_businesses(
    owner_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            category,
            latitude,
            longitude,
            address,
            offer,
            owner_id
        FROM businesses
        WHERE owner_id = ?
    """, (
        owner_id,
    ))

    businesses = cursor.fetchall()

    conn.close()

    return businesses


# =========================================================
# GET BUSINESS BY ID
# =========================================================

def get_business_by_id(
    business_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            category,
            latitude,
            longitude,
            address,
            offer,
            owner_id
        FROM businesses
        WHERE id = ?
    """, (
        business_id,
    ))

    business = cursor.fetchone()

    conn.close()

    return business


# =========================================================
# ASSIGN BUSINESS TO OWNER
# =========================================================

def assign_business_to_owner(
    business_id,
    owner_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE businesses
        SET owner_id = ?
        WHERE id = ?
    """, (
        owner_id,
        business_id
    ))

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    return updated


# =========================================================
# UPDATE OWNER OFFER
# =========================================================

def update_business_offer(
    business_id,
    owner_id,
    offer
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE businesses
        SET offer = ?
        WHERE id = ?
        AND owner_id = ?
    """, (
        offer,
        business_id,
        owner_id
    ))

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    return updated


# =========================================================
# SESSION HELPERS
# =========================================================

def create_session(
    token_hash,
    user_id,
    expires_at,
    created_at
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sessions
        (
            token_hash,
            user_id,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        token_hash,
        user_id,
        expires_at,
        created_at
    ))

    conn.commit()
    conn.close()


def get_session_user_id(
    token_hash,
    current_time
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id
        FROM sessions
        WHERE token_hash = ?
        AND expires_at > ?
    """, (
        token_hash,
        current_time
    ))

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else None


def delete_session(
    token_hash
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM sessions
        WHERE token_hash = ?
    """, (
        token_hash
    ))

    conn.commit()
    conn.close()


def delete_expired_sessions(
    current_time
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM sessions
        WHERE expires_at <= ?
    """, (
        current_time
    ))

    conn.commit()
    conn.close()


# =========================================================
# BUSINESS CLAIM REQUESTS
# =========================================================

def create_business_claim_request(business_id, owner_id, note, created_at):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, status FROM business_claim_requests
            WHERE business_id = ?
        """, (business_id,))
        existing = cursor.fetchone()
        if existing:
            if existing[1] != "rejected":
                raise sqlite3.IntegrityError("A claim already exists for this business.")
            cursor.execute("""
                UPDATE business_claim_requests
                SET owner_id = ?, note = ?, status = 'pending',
                    created_at = ?, reviewed_at = NULL, reviewed_by = NULL
                WHERE id = ?
            """, (owner_id, note, created_at, existing[0]))
            conn.commit()
            return existing[0]

        cursor.execute("""
            INSERT INTO business_claim_requests
                (business_id, owner_id, note, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        """, (business_id, owner_id, note, created_at))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_business_claim_requests(owner_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.business_id, b.name, b.address, c.note,
                   c.status, c.created_at
            FROM business_claim_requests c
            JOIN businesses b ON b.id = c.business_id
            WHERE c.owner_id = ?
            ORDER BY c.created_at DESC
        """, (owner_id,))
        return cursor.fetchall()
    finally:
        conn.close()


def review_business_claim_request(claim_id, status, reviewed_at, reviewed_by):
    if status not in ("approved", "rejected"):
        raise ValueError("status must be approved or rejected")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            SELECT business_id, owner_id, status
            FROM business_claim_requests
            WHERE id = ?
        """, (claim_id,))
        claim = cursor.fetchone()
        if not claim or claim[2] != "pending":
            conn.rollback()
            return {"result": "not_pending"}

        business_id, owner_id, _ = claim
        if status == "approved":
            cursor.execute("""
                UPDATE businesses SET owner_id = ?
                WHERE id = ? AND owner_id IS NULL
            """, (owner_id, business_id))
            if cursor.rowcount != 1:
                conn.rollback()
                return {"result": "already_claimed"}

        cursor.execute("""
            UPDATE business_claim_requests
            SET status = ?, reviewed_at = ?, reviewed_by = ?
            WHERE id = ? AND status = 'pending'
        """, (status, reviewed_at, reviewed_by, claim_id))
        if cursor.rowcount != 1:
            conn.rollback()
            return {"result": "not_pending"}

        conn.commit()
        return {"result": status, "business_id": business_id, "owner_id": owner_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_pending_business_claim_requests():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.business_id, b.name, b.address,
                   u.id, u.name, u.email, c.note, c.created_at
            FROM business_claim_requests c
            JOIN businesses b ON b.id = c.business_id
            JOIN users u ON u.id = c.owner_id
            WHERE c.status = 'pending'
            ORDER BY c.created_at ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()
