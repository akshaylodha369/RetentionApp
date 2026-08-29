import sqlite3

DB_NAME = "retention.db"


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    return sqlite3.connect(DB_NAME)


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

        cursor.execute("""
            SELECT id
            FROM businesses
            WHERE name = ? AND address = ?
        """, (
            business[0],
            business[4]
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
        """, business)

        added += 1

    conn.commit()
    conn.close()

    return added


# =========================================================
# FOLLOW BUSINESS
# =========================================================

def follow_business(user_id, business_id):

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

def unfollow_business(user_id, business_id):

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

def is_following(user_id, business_id):

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

def get_followed_businesses(user_id):

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
# USER FUNCTIONS
# =========================================================

# =========================================================
# GET USER BY EMAIL
# =========================================================

def get_user_by_email(email):

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

def get_user_by_id(user_id):

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
# OWNER FUNCTIONS
# =========================================================

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

def get_owner_businesses(owner_id):

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

def get_business_by_id(business_id):

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