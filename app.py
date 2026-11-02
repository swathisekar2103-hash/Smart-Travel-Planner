
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for
)
import requests
import os
import sqlite3
import re
import hashlib
from dotenv import load_dotenv

# APP SETUP
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_FILE, override=True)

GEOAPIFY_API_KEY = (os.getenv("GEOAPIFY_API_KEY") or "").strip()

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "smart-travel-planner-local-key"
)

HEADERS = {"User-Agent": "SmartTravelPlanner/1.0"}

# DATABASE SETUP
DATABASE = os.path.join(BASE_DIR, "database", "travel.db")
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_name TEXT NOT NULL,
            destination TEXT NOT NULL,
            travel_date TEXT DEFAULT '',
            days INTEGER DEFAULT 1,
            travel_type TEXT DEFAULT '',
            budget REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id INTEGER NOT NULL,
            place_id TEXT DEFAULT '',
            place_name TEXT NOT NULL,
            address TEXT DEFAULT '',
            image TEXT DEFAULT '',
            latitude REAL,
            longitude REAL,
            category TEXT DEFAULT '',
            FOREIGN KEY (package_id)
                REFERENCES packages(id)
                ON DELETE CASCADE,
            UNIQUE(package_id, place_name, address)
        )
    """)


    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id INTEGER NOT NULL,
            traveller_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            travellers INTEGER NOT NULL CHECK (travellers >= 1),
            price_per_person REAL NOT NULL,
            total_amount REAL NOT NULL,
            booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE
        )
    """)

    # Public feedback shared across all visitors of this website.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# INTEREST CATEGORIES
INTEREST_CONFIG = {
    "nature": {
        "title": "🌿 Nature",
        "categories": (
            "leisure.park,leisure.park.garden,"
            "natural.forest,natural.coastal,natural.mountain"
        ),
        "keyword": "nature park",
        "image": (
            "https://images.unsplash.com/photo-1441974231531-c6227db76b6e"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "food": {
        "title": "🍴 Food",
        "categories": (
            "catering.restaurant,catering.cafe,"
            "catering.fast_food,catering.food_court"
        ),
        "keyword": "restaurant food",
        "image": (
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "historical": {
        "title": "🏛️ Historical",
        "categories": "tourism.sights,building.historic",
        "keyword": "historic monument",
        "image": (
            "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "beach": {
        "title": "🏖️ Beach",
        "categories": "beach,natural.coastal,tourism.attraction",
        "keyword": "beach",
        "image": (
            "https://images.unsplash.com/photo-1507525428034-b723cf961d3e"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "shopping": {
        "title": "🛍️ Shopping",
        "categories": "commercial.shopping_mall,commercial.marketplace",
        "keyword": "shopping mall",
        "image": (
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "entertainment": {
        "title": "🎡 Entertainment",
        "categories": "entertainment,activity",
        "keyword": "entertainment",
        "image": (
            "https://images.unsplash.com/photo-1492684223066-81342ee5ff30"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "adventure": {
        "title": "🧗 Adventure",
        # Use Geoapify categories that are supported by the Places API.
        "categories": "tourism.attraction,leisure.park",
        "keyword": "adventure hiking",
        "image": (
            "https://images.unsplash.com/photo-1551632811-561732d1e306"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    },
    "photography": {
        "title": "📸 Photography",
        "categories": (
            "tourism.attraction.viewpoint,tourism.attraction,"
            "natural.coastal,natural.forest,leisure.park"
        ),
        "keyword": "scenic landscape",
        "image": (
            "https://images.unsplash.com/photo-1470770841072-f978cf4d019e"
            "?auto=format&fit=crop&w=1000&q=85"
        )
    }
}

# NEXT PART STARTS WITH GEOCODING

# GEOCODING

def geocode_destination(place, limit=5):
    # Qualify common Indian place names to avoid Geoapify matching a similarly
    # named locality in another district/country.
    original_place = clean_text(place)
    if original_place.casefold() in {"thanjavur", "tanjore"}:
        place = "Thanjavur, Tamil Nadu, India"

    if not GEOAPIFY_API_KEY:
        raise ValueError(
            "GEOAPIFY_API_KEY is missing in your .env file."
        )

    response = requests.get(
        "https://api.geoapify.com/v1/geocode/search",
        params={
            "text": place,
            "format": "json",
            "limit": limit,
            "lang": "en",
            "apiKey": GEOAPIFY_API_KEY
        },
        timeout=20
    )

    response.raise_for_status()
    return response.json().get("results", [])


# LOCATION HELPERS

def clean_text(value):
    if isinstance(value, str):
        return value.strip()
    return ""


def get_city(result):
    country = clean_text(result.get("country"))

    for value in [
        result.get("city"),
        result.get("municipality"),
        result.get("town"),
        result.get("village"),
        result.get("locality")
    ]:
        value = clean_text(value)

        if value and value.casefold() != country.casefold():
            return value

    return ""


def get_state(result):
    country = clean_text(result.get("country"))

    for value in [
        result.get("state"),
        result.get("province"),
        result.get("state_district"),
        result.get("region")
    ]:
        value = clean_text(value)

        if value and value.casefold() != country.casefold():
            return value

    return ""


def select_best_result(results, original_query):
    if not results:
        return None

    query = original_query.strip().casefold()
    if query in {"thanjavur", "tanjore"}:
        query = "thanjavur"
    exact_matches = []

    for item in results:
        values = [
            item.get("name"),
            item.get("city"),
            item.get("municipality"),
            item.get("town"),
            item.get("village"),
            item.get("formatted")
        ]

        if any(
            clean_text(value).casefold() == query
            for value in values
            if clean_text(value)
        ):
            exact_matches.append(item)

    candidates = exact_matches or results

    # For Thanjavur, prefer the Tamil Nadu, India result explicitly.
    if query == "thanjavur":
        tamil_nadu_matches = [
            item for item in candidates
            if clean_text(item.get("state")).casefold() == "tamil nadu"
            and clean_text(item.get("country")).casefold() == "india"
        ]
        if tamil_nadu_matches:
            candidates = tamil_nadu_matches

    locality_types = {
        "city", "town", "village", "municipality",
        "suburb", "district", "locality"
    }

    for item in candidates:
        result_type = clean_text(
            item.get("result_type")
        ).casefold()

        if result_type in locality_types and get_city(item):
            return item

    for item in candidates:
        city = get_city(item)

        if city and city.casefold() == query:
            return item

    for item in candidates:
        result_type = clean_text(
            item.get("result_type")
        ).casefold()

        country = clean_text(item.get("country"))
        name = clean_text(item.get("name"))

        if (
            result_type == "country"
            or (
                country
                and country.casefold() == query
                and (not name or name.casefold() == query)
            )
        ):
            return item

    return candidates[0]


def make_destination_data(result, original_query):
    city = get_city(result)
    state = get_state(result)
    country = clean_text(result.get("country"))

    result_type = clean_text(
        result.get("result_type")
    ).casefold()

    name = (
        clean_text(result.get("name"))
        or city
        or state
        or country
        or original_query
    )

    if result_type == "country":
        # A country such as Thailand does not have one single state/city.
        city = name or country
        state = "Not applicable"

    return {
        "name": name,
        "formatted": (
            clean_text(result.get("formatted"))
            or original_query
        ),
        # If geocoding returns a region/state without a city field,
        # display the matched destination name instead of "Not available".
        "city": city or name or clean_text(original_query) or "Not available",
        "state": state or "Not available",
        "country": country or "Not available",
        "latitude": result.get("lat"),
        "longitude": result.get("lon")
    }


# NEXT PART STARTS WITH IMAGE SEARCH

# IMAGE SEARCH

def get_place_image(place_name, destination, keyword, avoid_urls=None):
    """Return a category-appropriate fallback image with stable variation.

    Place-specific images from Geoapify are preferred when available. When the
    API has no image, use a varied category fallback rather than repeating one
    identical image for every card. These fallback photos are illustrative,
    not verified photos of the named place.
    """
    keyword_lower = (keyword or "").casefold()

    image_pools = {
        "food": [
            "photo-1517248135467-4c7edcad34c4",
            "photo-1514933651103-005eec06c04b",
            "photo-1555396273-367ea4eb4db5",
            "photo-1414235077428-338989a2e8c0",
            "photo-1559339352-11d035aa65de",
            "photo-1559305616-3f99cd43e353",
            "photo-1552566626-52f8b828add9",
            "photo-1550966871-3ed3cdb5ed0c",
            "photo-1414235077428-338989a2e8c0",
            "photo-1515003197210-e0cd7184f8b5",
        ],
        "beach": [
            "photo-1507525428034-b723cf961d3e",
            "photo-1519046904884-53103b34b206",
            "photo-1473116763249-2faaef81ccda",
            "photo-1506953823976-52e1fdc0149a",
            "photo-1498307833015-e7b400441eb8",
            "photo-1510414842594-a61c69b5ae57",
            "photo-1518837695005-2083093ee35b",
            "photo-1493558103817-58b2924bce98",
            "photo-1500375592092-40eb2168fd21",
            "photo-1519046904884-53103b34b206",
        ],
        "historical": [
            "photo-1464822759023-fed622ff2c3b",
            "photo-1511818966892-d7d671e672a2",
            "photo-1564507592333-c60657eea523",
            "photo-1533929736458-ca588d08c8be",
            "photo-1524492412937-b28074a5d7da",
            "photo-1548013146-72479768bada",
            "photo-1568322445389-f64ac2515020",
            "photo-1603565816030-6b389eeb23cb",
            "photo-1590073242678-70ee3fc28e8e",
            "photo-1511818966892-d7d671e672a2",
        ],
        "shopping": [
            "photo-1441986300917-64674bd600d8",
            "photo-1483985988355-763728e1935b",
            "photo-1519567241046-7f570eee3ce6",
            "photo-1555529669-e69e7aa0ba9a",
            "photo-1607082349566-187342175e2f",
            "photo-1472851294608-062f824d29cc",
            "photo-1555529669-e69e7aa0ba9a",
            "photo-1604719312566-8912e9c8a213",
            "photo-1607083206968-13611e3d76db",
            "photo-1519567241046-7f570eee3ce6",
        ],
        "entertainment": [
            "photo-1492684223066-81342ee5ff30",
            "photo-1501386761578-eac5c94b800a",
            "photo-1459749411175-04bf5292ceea",
            "photo-1506157786151-b8491531f063",
            "photo-1470229722913-7c0e2dbbafd3",
            "photo-1506157786151-b8491531f063",
            "photo-1501386761578-eac5c94b800a",
            "photo-1514525253161-7a46d19cd819",
            "photo-1459749411175-04bf5292ceea",
            "photo-1492684223066-81342ee5ff30",
        ],
        "adventure": [
            "photo-1551632811-561732d1e306",
            "photo-1464822759023-fed622ff2c3b",
            "photo-1551632811-561732d1e306",
            "photo-1472396961693-142e6e269027",
            "photo-1500534623283-312aade485b7",
            "photo-1464822759023-fed622ff2c3b",
            "photo-1472396961693-142e6e269027",
            "photo-1519681393784-d120267933ba",
            "photo-1464278533981-50106e6176b1",
            "photo-1500530855697-b586d89ba3ee",
        ],
        "nature": [
            "photo-1441974231531-c6227db76b6e",
            "photo-1470770841072-f978cf4d019e",
            "photo-1500530855697-b586d89ba3ee",
            "photo-1472396961693-142e6e269027",
            "photo-1433086966358-54859d0ed716",
            "photo-1500530855697-b586d89ba3ee",
            "photo-1511497584788-876760111969",
            "photo-1448375240586-882707db888b",
            "photo-1472396961693-142e6e269027",
            "photo-1500534623283-312aade485b7",
        ],
        "photography": [
            "photo-1470770841072-f978cf4d019e",
            "photo-1500530855697-b586d89ba3ee",
            "photo-1464822759023-fed622ff2c3b",
            "photo-1501785888041-af3ef285b470",
            "photo-1472396961693-142e6e269027",
            "photo-1511497584788-876760111969",
            "photo-1500534623283-312aade485b7",
            "photo-1519681393784-d120267933ba",
            "photo-1433086966358-54859d0ed716",
            "photo-1441974231531-c6227db76b6e",
        ],
    }

    if "food" in keyword_lower or "restaurant" in keyword_lower:
        fallback_key = "food"
    elif "beach" in keyword_lower:
        fallback_key = "beach"
    elif "historic" in keyword_lower or "monument" in keyword_lower:
        fallback_key = "historical"
    elif "shopping" in keyword_lower:
        fallback_key = "shopping"
    elif "entertainment" in keyword_lower:
        fallback_key = "entertainment"
    elif "adventure" in keyword_lower or "hiking" in keyword_lower:
        fallback_key = "adventure"
    elif "nature" in keyword_lower or "park" in keyword_lower:
        fallback_key = "nature"
    else:
        fallback_key = "photography"

    pool = image_pools[fallback_key]
    seed = f"{place_name}|{destination}|{keyword}".casefold().encode("utf-8")
    index = int(hashlib.sha256(seed).hexdigest(), 16) % len(pool)
    avoided = set(avoid_urls or [])

    # Pick the first unused fallback URL where possible, so cards in one
    # interest section do not all show the same stock image.
    for offset in range(len(pool)):
        candidate = pool[(index + offset) % len(pool)]
        image = f"https://images.unsplash.com/{candidate}?auto=format&fit=crop&w=1000&q=85"
        if image not in avoided:
            return {"image": image, "source": ""}

    image = f"https://images.unsplash.com/{pool[index]}?auto=format&fit=crop&w=1000&q=85"
    return {"image": image, "source": ""}


# SEARCH PLACES NEAR DESTINATION

def search_places(latitude, longitude, categories, destination, keyword):
    """Find, validate, and de-duplicate nearby places from Geoapify."""
    if latitude is None or longitude is None:
        return []
    if not GEOAPIFY_API_KEY:
        print("Geoapify Places API: missing API key")
        return []

    keyword_lower = (keyword or "").casefold()

    # Keep queries as specific as possible to avoid irrelevant results.
    if "food" in keyword_lower or "restaurant" in keyword_lower:
        category_queries = ["catering.restaurant", "catering.cafe", "catering.fast_food"]
    elif "beach" in keyword_lower:
        category_queries = ["beach", "natural.coast", "tourism.attraction"]
    elif "historic" in keyword_lower or "monument" in keyword_lower:
        category_queries = ["building.historic", "tourism.sights", "tourism.attraction"]
    elif "shopping" in keyword_lower:
        category_queries = ["commercial.shopping_mall", "commercial.marketplace"]
    elif "entertainment" in keyword_lower:
        category_queries = ["entertainment", "activity"]
    elif "adventure" in keyword_lower or "hiking" in keyword_lower:
        category_queries = ["sport", "tourism.attraction", "natural.mountain"]
    elif "nature" in keyword_lower or "scenic" in keyword_lower:
        category_queries = ["leisure.park", "natural.forest", "natural.water", "tourism.attraction"]
    else:
        category_queries = ["tourism.attraction", "tourism.sights"]

    generic_names = {
        "playing area", "play area", "playground", "park", "nature park",
        "tourist attraction", "attraction", "restaurant", "cafe", "shop",
        "shopping mall", "open space", "vacant land", "unnamed road",
        "unnamed place", "unknown", "point of interest", "picnic area"
    }
    seen_ids = set()
    seen_name_addresses = set()
    seen_coordinates = set()
    seen_image_urls = set()
    places = []

    def normalize(value):
        value = clean_text(value).casefold()
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    for category_query in category_queries:
        try:
            response = requests.get(
                "https://api.geoapify.com/v2/places",
                params={
                    "categories": category_query,
                    # A tighter search radius keeps recommendations close to
                    # the selected city instead of returning distant towns.
                    "filter": f"circle:{longitude},{latitude},20000",
                    "bias": f"proximity:{longitude},{latitude}",
                    "limit": 50,
                    "lang": "en",
                    "apiKey": GEOAPIFY_API_KEY,
                },
                headers=HEADERS,
                timeout=20,
            )

            if response.status_code == 400:
                print(
                    f"Geoapify ignored unsupported category '{category_query}': "
                    f"{response.text[:250]}"
                )
                continue

            response.raise_for_status()
            features = response.json().get("features", [])

            for feature in features:
                properties = feature.get("properties", {}) or {}
                name = clean_text(properties.get("name"))
                if not name:
                    continue

                normalized_name = normalize(name)
                if not normalized_name or normalized_name in generic_names:
                    continue

                formatted = clean_text(properties.get("formatted"))

                if (destination or "").strip().casefold() in {"thanjavur", "tanjore"}:
                    place_state = clean_text(properties.get("state")).casefold()
                    place_country = clean_text(properties.get("country")).casefold()
                    address_lower = formatted.casefold()
                    if place_country and place_country != "india":
                        continue
                    if place_state and place_state != "tamil nadu":
                        continue
                    if not place_state and "tamil nadu" not in address_lower and "india" not in address_lower:
                        continue

                normalized_address = normalize(formatted)
                place_id = clean_text(properties.get("place_id"))
                lat = properties.get("lat")
                lon = properties.get("lon")

                # Deduplicate by provider ID, then by normalized name/address,
                # and finally by near-identical coordinates.
                if place_id and place_id in seen_ids:
                    continue
                name_address_key = (normalized_name, normalized_address)
                if name_address_key in seen_name_addresses:
                    continue

                coord_key = None
                try:
                    if lat is not None and lon is not None:
                        coord_key = (round(float(lat), 4), round(float(lon), 4))
                except (TypeError, ValueError):
                    coord_key = None
                if coord_key and coord_key in seen_coordinates:
                    continue

                category_list = properties.get("categories", [])
                category = (
                    category_list[0]
                    if isinstance(category_list, list) and category_list
                    else category_query
                )

                # Reject obviously unrelated results for category-specific searches.
                category_text = " ".join(category_list).casefold() if isinstance(category_list, list) else ""
                if "food" in keyword_lower or "restaurant" in keyword_lower:
                    if not any(token in category_text for token in ("catering",)):
                        continue
                elif "shopping" in keyword_lower:
                    if "commercial" not in category_text:
                        continue
                elif "historic" in keyword_lower or "monument" in keyword_lower:
                    if not any(token in category_text for token in ("historic", "tourism.sights", "tourism.attraction")):
                        continue
                elif "beach" in keyword_lower:
                    if not any(token in category_text for token in ("beach", "coast", "natural", "tourism.attraction")):
                        continue

                media = properties.get("wiki_and_media") or {}
                image = ""
                image_source = ""
                if isinstance(media, dict):
                    image = clean_text(media.get("image"))
                    image_source = clean_text(media.get("descriptionurl"))

                # If no place-specific image exists, use a varied category fallback.
                # If the provider repeats an image URL, also replace it with a fallback.
                if not image or image in seen_image_urls:
                    image_data = get_place_image(name, destination, keyword, seen_image_urls)
                    image = image_data.get("image", "")
                    image_source = image_data.get("source", "")

                # Ensure fallback selection is unique within this result list.
                if image in seen_image_urls:
                    image_data = get_place_image(
                        name + " " + (formatted or place_id or str(len(places))),
                        destination,
                        keyword,
                        seen_image_urls,
                    )
                    image = image_data.get("image", "")

                if place_id:
                    seen_ids.add(place_id)
                seen_name_addresses.add(name_address_key)
                if coord_key:
                    seen_coordinates.add(coord_key)
                if image:
                    seen_image_urls.add(image)

                places.append({
                    "name": name,
                    "address": formatted or destination,
                    "city": get_city(properties) or destination,
                    "state": get_state(properties),
                    "country": clean_text(properties.get("country")),
                    "latitude": lat,
                    "longitude": lon,
                    "place_id": place_id,
                    "category": category,
                    "image": image,
                    "image_source": image_source,
                })

                if len(places) >= 10:
                    break

            if len(places) >= 10:
                break

        except (requests.RequestException, ValueError) as error:
            print(f"Geoapify Places API error for '{category_query}': {error}")
            if isinstance(error, requests.HTTPError) and error.response is not None:
                print("Geoapify response:", error.response.text[:500])
            continue

    print(
        f"Place search for destination={destination!r}, interest={keyword!r}: "
        f"{len(places)} relevant unique places found"
    )
    return places


# NEXT PART STARTS WITH FLASK ROUTES

# HOME

@app.route("/")
def home():
    return render_template("index.html")


# ABOUT PAGE

@app.route("/about")
def about():
    return render_template("about.html")


# ==================================================
# FEEDBACK PAGE - ALL VISITORS CAN READ PUBLIC FEEDBACK
# ==================================================

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    error = None
    success = request.args.get("success", "")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        try:
            rating = int(request.form.get("rating", "0"))
        except (TypeError, ValueError):
            rating = 0

        if not name or not email or not message:
            error = "Please fill in all fields."
        elif len(name) > 80 or len(email) > 254 or len(message) > 2000:
            error = "Please keep your name, email and feedback within the allowed length."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            error = "Please enter a valid email address."
        elif rating < 1 or rating > 5:
            error = "Please select a rating from 1 to 5."
        else:
            conn = get_db()
            try:
                conn.execute(
                    """
                    INSERT INTO feedback (name, email, rating, message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, email, rating, message)
                )
                conn.commit()
            finally:
                conn.close()

            return redirect(url_for("feedback", success="Your feedback was submitted successfully."))

    conn = get_db()
    try:
        # Email is deliberately not sent to the template or shown publicly.
        feedbacks = conn.execute(
            """
            SELECT id, name, rating, message, created_at
            FROM feedback
            ORDER BY id DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return render_template(
        "feedback.html",
        feedbacks=feedbacks,
        error=error,
        success=success
    )


# DESTINATIONS PAGE

@app.route("/destinations")
def destinations():
    return render_template("destinations.html")


# DESTINATION SEARCH API

@app.route("/search-destination", methods=["GET"])
def search_destination():
    place = request.args.get("q", "").strip()

    if not place:
        return jsonify({
            "results": [],
            "error": "Please enter a destination."
        }), 400

    try:
        results_data = geocode_destination(place, limit=5)
        results = []

        for item in results_data:
            result_type = clean_text(item.get("result_type")).casefold()
            country_name = clean_text(item.get("country")) or "Not available"
            city_name = get_city(item)
            state_name = get_state(item)
            if result_type == "country":
                city_name = clean_text(item.get("name")) or country_name
                state_name = "Not applicable"

            results.append({
                "name": (
                    clean_text(item.get("name"))
                    or city_name
                    or country_name
                    or place
                ),
                "address": clean_text(item.get("formatted")) or place,
                "city": city_name or "Not available",
                "state": state_name or "Not available",
                "country": country_name,
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "result_type": result_type
            })

        return jsonify({"results": results})

    except ValueError as error:
        return jsonify({
            "results": [],
            "error": str(error)
        }), 500

    except requests.RequestException as error:
        print("Destination search error:", error)
        return jsonify({
            "results": [],
            "error": (
                "Unable to connect to destination search. "
                "Check your internet and API key."
            )
        }), 502


# PLACE DETAILS

@app.route("/place/<path:place_id>")
def place_details(place_id):
    if not GEOAPIFY_API_KEY:
        return render_template(
            "place_details.html",
            error="API key is not connected yet.",
            packages=[]
        )

    destination_name = request.args.get("destination", "")
    selected_image = request.args.get("image", "")
    image_source = request.args.get("image_source", "")

    try:
        response = requests.get(
            "https://api.geoapify.com/v2/place-details",
            params={
                "id": place_id,
                "apiKey": GEOAPIFY_API_KEY,
                "lang": "en",
                "features": "details"
            },
            timeout=20
        )

        response.raise_for_status()
        features = response.json().get("features", [])

        if not features:
            return render_template(
                "place_details.html",
                error="Place details not found.",
                packages=[]
            )

        properties = features[0].get("properties", {})

        name = properties.get("name") or "Unknown Place"
        address = (
            properties.get("formatted")
            or destination_name
            or "Not available"
        )

        city = get_city(properties) or "Not available"
        state = get_state(properties) or "Not available"
        country = (
            clean_text(properties.get("country"))
            or "Not available"
        )

        categories = properties.get("categories", [])
        category = (
            categories[0]
            if isinstance(categories, list) and categories
            else "Tourist Place"
        )

        media = properties.get("wiki_and_media") or {}
        image = ""

        if isinstance(media, dict):
            image = media.get("image", "")
            image_source = (
                image_source
                or media.get("descriptionurl", "")
            )

        if not image:
            image = selected_image

        if not image:
            image_data = get_place_image(
                name, destination_name, "scenic landscape"
            )
            image = image_data["image"]
            image_source = image_source or image_data["source"]

        place_data = {
            "place_id": place_id,
            "name": name,
            "address": address,
            "city": city,
            "state": state,
            "country": country,
            "latitude": properties.get("lat"),
            "longitude": properties.get("lon"),
            "category": category,
            "image": image,
            "image_source": image_source,
            "destination": destination_name or city
        }

        conn = get_db()
        packages = conn.execute("""
            SELECT id, package_name, destination
            FROM packages
            ORDER BY created_at DESC, id DESC
        """).fetchall()
        conn.close()

        return render_template(
            "place_details.html",
            place=place_data,
            packages=packages
        )

    except (requests.RequestException, ValueError) as error:
        print("Place details error:", error)
        return render_template(
            "place_details.html",
            error="Unable to load place details.",
            packages=[]
        )


# CREATE A NEW PACKAGE

@app.route("/create-package", methods=["POST"])
def create_package():
    destination = request.form.get(
        "destination", ""
    ).strip()

    package_name = request.form.get(
        "package_name", ""
    ).strip()

    travel_date = request.form.get("travel_date", "").strip()
    travel_type = request.form.get("travel_type", "").strip()

    try:
        days = max(1, int(request.form.get("days", 1)))
    except (TypeError, ValueError):
        days = 1

    try:
        budget = max(
            0, float(request.form.get("budget", 0) or 0)
        )
    except (TypeError, ValueError):
        budget = 0

    if not destination:
        return redirect(url_for(
            "my_packages",
            message="Enter a destination first."
        ))

    if not package_name:
        package_name = destination + " Trip"

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO packages (
            package_name, destination, travel_date,
            days, travel_type, budget
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        package_name, destination, travel_date,
        days, travel_type, budget
    ))

    package_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return redirect(url_for(
        "my_packages",
        message="Package created successfully.",
        selected=package_id
    ))


# NEXT PART: ADD PLACES, MY PACKAGES & PLAN TRIP

# ==================================================
# ADD PLACE TO PACKAGE
# ==================================================

@app.route("/add-to-package", methods=["POST"])
def add_to_package():
    place_id = request.form.get("place_id", "").strip()
    place_name = request.form.get("place_name", "").strip()
    address = request.form.get("address", "").strip()
    image = request.form.get("image", "").strip()
    category = request.form.get("category", "").strip()

    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()

    package_id_input = request.form.get("package_id", "").strip()
    destination = (
        request.form.get("new_destination", "").strip()
        or request.form.get("destination", "").strip()
        or address
        or place_name
    )
    package_name = (
        request.form.get("new_package_name", "").strip()
        or f"{destination} Trip"
    )

    try:
        days = max(1, int(request.form.get("days", 1)))
    except (ValueError, TypeError):
        days = 1

    try:
        budget = max(0, float(request.form.get("budget", 0) or 0))
    except (ValueError, TypeError):
        budget = 0

    travel_date = request.form.get("travel_date", "").strip()
    travel_type = request.form.get("travel_type", "Solo").strip()

    if not place_name:
        return redirect(url_for("my_packages", message="Place name is missing."))

    try:
        latitude = float(latitude) if latitude else None
    except ValueError:
        latitude = None

    try:
        longitude = float(longitude) if longitude else None
    except ValueError:
        longitude = None

    conn = get_db()

    try:
        package_id = None

        if package_id_input.isdigit():
            existing = conn.execute(
                "SELECT id FROM packages WHERE id = ?",
                (int(package_id_input),)
            ).fetchone()

            if existing:
                package_id = existing["id"]

        if package_id is None:
            cursor = conn.execute(
                """
                INSERT INTO packages
                (destination, package_name, travel_date, days,
                 travel_type, budget)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    destination,
                    package_name,
                    travel_date,
                    days,
                    travel_type,
                    budget
                )
            )
            package_id = cursor.lastrowid

        conn.execute(
            """
            INSERT OR IGNORE INTO package_places
            (package_id, place_id, place_name, address, image,
             latitude, longitude, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                place_id or place_name,
                place_name,
                address,
                image,
                latitude,
                longitude,
                category
            )
        )

        conn.commit()

    except sqlite3.Error as error:
        conn.rollback()
        print("Database error:", error)
        return redirect(
            url_for("my_packages", message="Could not save this place.")
        )

    finally:
        conn.close()

    return redirect(url_for("package_details", package_id=package_id))


# ==================================================
# MY PACKAGES
# ==================================================

@app.route("/my-packages")
def my_packages():
    message = request.args.get("message", "")
    selected_package = request.args.get("selected_package", "")

    conn = get_db()

    try:
        packages = conn.execute(
            """
            SELECT p.*,
                   COUNT(pp.id) AS place_count
            FROM packages p
            LEFT JOIN package_places pp
                ON p.id = pp.package_id
            GROUP BY p.id
            ORDER BY p.id DESC
            """
        ).fetchall()

    finally:
        conn.close()

    return render_template(
        "my_packages.html",
        packages=packages,
        message=message,
        selected_package=selected_package
    )


# ==================================================
# PACKAGE DETAILS
# ==================================================

@app.route("/package/<int:package_id>")
def package_details(package_id):
    conn = get_db()

    try:
        package = conn.execute(
            "SELECT * FROM packages WHERE id = ?",
            (package_id,)
        ).fetchone()

        if package is None:
            return redirect(
                url_for("my_packages", message="Package not found.")
            )

        places = conn.execute(
            """
            SELECT *
            FROM package_places
            WHERE package_id = ?
            ORDER BY id DESC
            """,
            (package_id,)
        ).fetchall()

    finally:
        conn.close()

    return render_template(
        "packages_details.html",
        package=package,
        places=places
    )


# ==================================================
# PACKAGE BOOKING
# ==================================================

@app.route("/book/<int:package_id>", methods=["GET", "POST"])
def book_package(package_id):
    conn = get_db()

    try:
        package = conn.execute(
            "SELECT * FROM packages WHERE id = ?",
            (package_id,)
        ).fetchone()

        if package is None:
            return redirect(
                url_for("my_packages", message="Package not found.")
            )

        if request.method == "POST":
            traveller_name = request.form.get("traveller_name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()

            try:
                travellers = int(request.form.get("travellers", "1"))
            except (ValueError, TypeError):
                travellers = 0

            try:
                price_per_person = float(package["budget"] or 0)
            except (ValueError, TypeError):
                price_per_person = 0.0

            if (
                not traveller_name
                or not email
                or not phone
                or travellers < 1
            ):
                return render_template(
                    "booking.html",
                    package=package,
                    error="Please fill all fields and enter at least 1 traveller."
                )

            total_amount = price_per_person * travellers

            cursor = conn.execute(
                """
                INSERT INTO bookings (
                    package_id, traveller_name, email, phone, travellers,
                    price_per_person, total_amount
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    traveller_name,
                    email,
                    phone,
                    travellers,
                    price_per_person,
                    total_amount
                )
            )
            booking_id = cursor.lastrowid
            conn.commit()

            return redirect(
                url_for("booking_confirmation", booking_id=booking_id)
            )

    finally:
        conn.close()

    return render_template("booking.html", package=package, error=None)


@app.route("/booking-confirmation/<int:booking_id>")
def booking_confirmation(booking_id):
    conn = get_db()

    try:
        booking = conn.execute(
            """
            SELECT bookings.*, packages.package_name, packages.destination
            FROM bookings
            JOIN packages ON bookings.package_id = packages.id
            WHERE bookings.id = ?
            """,
            (booking_id,)
        ).fetchone()
    finally:
        conn.close()

    if booking is None:
        return "Booking not found.", 404

    return render_template(
        "booking_confirmation.html",
        booking=booking
    )


# ==================================================
# REMOVE PLACE FROM PACKAGE
# ==================================================

@app.route(
    "/remove-from-package/<int:place_row_id>",
    methods=["POST"]
)
def remove_from_package(place_row_id):
    conn = get_db()

    try:
        place = conn.execute(
            """
            SELECT package_id
            FROM package_places
            WHERE id = ?
            """,
            (place_row_id,)
        ).fetchone()

        if place is None:
            return redirect(
                url_for("my_packages", message="Place not found.")
            )

        package_id = place["package_id"]

        conn.execute(
            "DELETE FROM package_places WHERE id = ?",
            (place_row_id,)
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(
        url_for("package_details", package_id=package_id)
    )


# ==================================================
# DELETE COMPLETE PACKAGE
# ==================================================

@app.route(
    "/delete-package/<int:package_id>",
    methods=["POST"]
)
def delete_package(package_id):
    conn = get_db()

    try:
        conn.execute(
            "DELETE FROM package_places WHERE package_id = ?",
            (package_id,)
        )

        conn.execute(
            "DELETE FROM packages WHERE id = ?",
            (package_id,)
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(
        url_for("my_packages", message="Package deleted.")
    )


# ==================================================
# PLAN TRIP
# ==================================================

@app.route("/plan-trip", methods=["GET", "POST"])
def plan_trip():
    if request.method == "GET":
        return render_template("plan_trip.html")

    destination = request.form.get("destination", "").strip()
    travel_date = request.form.get("travel_date", "").strip()
    travel_type = request.form.get("travel_type", "Solo").strip()

    try:
        days = max(1, int(request.form.get("days", 1)))
    except (ValueError, TypeError):
        days = 1

    try:
        budget = max(0, float(request.form.get("budget", 0) or 0))
    except (ValueError, TypeError):
        budget = 0

    interests = request.form.getlist("interests")
    recommendations = []
    interest_results = {}

    if not destination:
        return render_template(
            "plan_trip.html",
            error="Please enter a destination.",
            destination=destination,
            destination_name=destination,
            recommendations=recommendations,
            interest_results=interest_results,
            selected_interests=interests,
            travel_date=travel_date, days=days,
            travel_type=travel_type, budget=budget
        )

    if not GEOAPIFY_API_KEY:
        return render_template(
            "plan_trip.html",
            error="API key is not connected yet. Check GEOAPIFY_API_KEY in your .env file.",
            destination=destination,
            destination_name=destination,
            recommendations=recommendations,
            interest_results=interest_results,
            selected_interests=interests,
            travel_date=travel_date, days=days,
            travel_type=travel_type, budget=budget
        )

    destination_data = None
    try:
        geo_results = geocode_destination(destination)
        if not geo_results:
            return render_template(
                "plan_trip.html",
                error=f"Destination '{destination}' was not found. Try a city name such as Goa or Chennai.",
                destination=destination,
                destination_name=destination,
                recommendations=recommendations,
                interest_results=interest_results,
                selected_interests=interests,
                travel_date=travel_date, days=days,
                travel_type=travel_type, budget=budget
            )

        best_result = select_best_result(geo_results, destination)
        if not best_result:
            return render_template(
                "plan_trip.html",
                error="Could not identify this destination. Please try another name.",
                destination=destination,
                destination_name=destination,
                recommendations=recommendations,
                interest_results=interest_results,
                selected_interests=interests,
                travel_date=travel_date, days=days,
                travel_type=travel_type, budget=budget
            )

        destination_data = make_destination_data(best_result, destination)

        latitude = destination_data.get("latitude")
        longitude = destination_data.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError("The destination search did not return coordinates. Try a city or town name.")

        for interest in interests:
            config = INTEREST_CONFIG.get(interest)
            if not config:
                continue

            try:
                places = search_places(
                    latitude,
                    longitude,
                    config["categories"],
                    destination,
                    config["keyword"]
                )

                for place in places:
                    place["interest"] = interest
                    place["interest_title"] = config["title"]

                # Keep the results available by interest key.
                interest_results[interest] = places

                # plan_trip.html expects each recommendation to contain
                # a section title and a list of places.
                recommendations.append({
                    "title": config["title"],
                    "places": places
                })

            except (requests.RequestException, ValueError) as error:
                print(f"Search error for {interest}: {error}")
                interest_results[interest] = []
                recommendations.append({
                    "title": config["title"],
                    "places": []
                })

        if interests and not recommendations:
            print("No places returned. Check the Geoapify API key, usage limits, and selected category names.")

        return render_template(
            "plan_trip.html",
            destination=destination_data,
            destination_data=destination_data,
            destination_info=destination_data,
            destination_name=(destination_data.get("name", destination) if destination_data else destination),
            recommendations=recommendations,
            interest_results=interest_results,
            selected_interests=interests,
            travel_date=travel_date,
            days=days,
            travel_type=travel_type,
            budget=budget,
            error=("No places were returned for the selected interests. Try another interest or check the API key." if interests and not recommendations else None)
        )

    except requests.RequestException as error:
        print("Geoapify connection error:", error)
        return render_template(
            "plan_trip.html",
            error="Could not connect to the travel service. Check your internet and Geoapify API key, then try again.",
            destination=destination,
            destination_data=destination_data,
            destination_info=destination_data,
            destination_name=(destination_data.get("name", destination) if destination_data else destination),
            recommendations=recommendations,
            interest_results=interest_results,
            selected_interests=interests,
            travel_date=travel_date, days=days,
            travel_type=travel_type, budget=budget
        )
    except (ValueError, KeyError, TypeError) as error:
        print("Trip planning error:", error)
        return render_template(
            "plan_trip.html",
            error=str(error),
            destination=destination,
            destination_data=destination_data,
            destination_info=destination_data,
            destination_name=(destination_data.get("name", destination) if destination_data else destination),
            recommendations=recommendations,
            interest_results=interest_results,
            selected_interests=interests,
            travel_date=travel_date, days=days,
            travel_type=travel_type, budget=budget
        )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)
