import sqlite3


def create_database():

    conn = sqlite3.connect("database/travel.db")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destination TEXT NOT NULL,
            travel_date TEXT NOT NULL,
            days INTEGER NOT NULL,
            budget REAL NOT NULL,
            travel_type TEXT NOT NULL,
            interests TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_trip(destination, travel_date, days, budget, travel_type, interests):

    conn = sqlite3.connect("database/travel.db")

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trips
        (destination, travel_date, days, budget, travel_type, interests)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        destination,
        travel_date,
        days,
        budget,
        travel_type,
        interests
    ))

    conn.commit()
    conn.close()