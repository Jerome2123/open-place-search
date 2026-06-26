from __future__ import annotations

import re

from open_places_manticore.models import PlaceType

_CATEGORY_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")

TYPE_CATEGORY_IDS: dict[PlaceType, int] = {
    PlaceType.LOCATION: 10,
    PlaceType.ATTRACTION: 100,
    PlaceType.DINING: 200,
    PlaceType.LODGING: 300,
    PlaceType.TRANSPORT: 400,
    PlaceType.VENUE: 500,
    PlaceType.GENERIC: 900,
}

SPECIFIC_CATEGORY_IDS: dict[str, int] = {
    "tourist_attraction": 100,
    "attraction": 100,
    "museum": 110,
    "art_gallery": 111,
    "park": 120,
    "national_park": 121,
    "historical_landmark": 130,
    "archaeological_site": 131,
    "monument": 132,
    "market": 140,
    "restaurant": 200,
    "bar": 210,
    "cafe": 220,
    "bakery": 221,
    "hotel": 300,
    "lodging": 300,
    "resort": 310,
    "airport": 400,
    "train_station": 410,
    "station": 410,
    "event_venue": 500,
    "stadium": 510,
    "city": 20,
    "region": 30,
    "country": 40,
    "neighborhood": 50,
}

SUBTYPE_ALIASES: dict[str, str] = {
    "lodging": "hotel",
    "resort_hotel": "hotel",
    "locality": "city",
    "village": "city",
    "town": "city",
    "administrative": "region",
    "administrative_area_level_1": "region",
    "administrative_area_level_2": "region",
    "protected_area": "national_park",
}

_LOCATION_SUBTYPES = {"country", "region", "city", "neighborhood"}
_DINING_SUBTYPES = {"restaurant", "bar", "cafe", "bakery"}
_LODGING_SUBTYPES = {"hotel", "resort"}
_TRANSPORT_SUBTYPES = {"airport", "train_station", "station"}
_VENUE_SUBTYPES = {"event_venue", "stadium", "concert_hall", "performing_arts_theater"}
_ATTRACTION_SUBTYPES = {
    "tourist_attraction",
    "attraction",
    "museum",
    "art_gallery",
    "park",
    "national_park",
    "historical_landmark",
    "monument",
    "archaeological_site",
    "castle",
    "ruins",
    "memorial",
    "place_of_worship",
    "beach",
    "peak",
    "waterfall",
    "volcano",
    "zoo",
    "aquarium",
    "market",
}


def normalize_category(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = text.replace(":", "_").replace("=", "_")
    return re.sub(r"_+", "_", text).strip("_")


def canonical_subtype(value: object) -> str | None:
    normalized = normalize_category(value)
    if not normalized:
        return None
    return SUBTYPE_ALIASES.get(normalized, normalized)


def choose_subtype(categories: list[str], basic_category: str | None = None) -> str | None:
    ordered = [canonical_subtype(category) for category in categories]
    if basic_category:
        ordered.append(canonical_subtype(basic_category))
    preferred = [
        "bar",
        "restaurant",
        "cafe",
        "hotel",
        "airport",
        "train_station",
        "museum",
        "market",
        "tourist_attraction",
        "park",
        "national_park",
        "event_venue",
        "stadium",
        "city",
        "region",
        "country",
        "neighborhood",
    ]
    present = [item for item in ordered if item]
    for subtype in preferred:
        if subtype in present:
            return subtype
    return present[0] if present else None


def place_type_from_subtype(subtype: str | None) -> PlaceType:
    subtype = canonical_subtype(subtype)
    if subtype in _LOCATION_SUBTYPES:
        return PlaceType.LOCATION
    if subtype in _DINING_SUBTYPES:
        return PlaceType.DINING
    if subtype in _LODGING_SUBTYPES:
        return PlaceType.LODGING
    if subtype in _TRANSPORT_SUBTYPES:
        return PlaceType.TRANSPORT
    if subtype in _VENUE_SUBTYPES:
        return PlaceType.VENUE
    if subtype in _ATTRACTION_SUBTYPES:
        return PlaceType.ATTRACTION
    return PlaceType.GENERIC


def category_text(categories: list[str], subtype: str | None = None) -> str:
    values = [subtype or "", *categories]
    seen: set[str] = set()
    tokens: list[str] = []
    for value in values:
        normalized = normalize_category(value)
        if not normalized:
            continue
        for token in _CATEGORY_TOKEN_PATTERN.sub(" ", normalized).split():
            if token and token not in seen:
                seen.add(token)
                tokens.append(token)
    return " ".join(tokens)


def category_ids(place_type: PlaceType, subtype: str | None, categories: list[str]) -> list[int]:
    ids: list[int] = [TYPE_CATEGORY_IDS.get(place_type, TYPE_CATEGORY_IDS[PlaceType.GENERIC])]
    for value in [subtype or "", *categories]:
        normalized = canonical_subtype(value)
        category_id = SPECIFIC_CATEGORY_IDS.get(normalized or "")
        if category_id is not None and category_id not in ids:
            ids.append(category_id)
    return ids


def type_compatible(left: PlaceType, right: PlaceType) -> bool:
    if left == right:
        return True
    if PlaceType.GENERIC in {left, right}:
        return left in {PlaceType.GENERIC, PlaceType.ATTRACTION, PlaceType.DINING, PlaceType.TRANSPORT} and right in {
            PlaceType.GENERIC,
            PlaceType.ATTRACTION,
            PlaceType.DINING,
            PlaceType.TRANSPORT,
        }
    return False
