from __future__ import annotations

import bz2
import gzip
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from open_place_search.models import Provider, SourceRecord
from open_place_search.normalization import dedupe_text
from open_place_search.taxonomy import choose_subtype, place_type_from_subtype

GEONAMES_COLUMNS = [
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature class",
    "feature code",
    "country code",
    "cc2",
    "admin1 code",
    "admin2 code",
    "admin3 code",
    "admin4 code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification date",
]

_WKT_POINT_RE = re.compile(
    r"Point\s*\(\s*(?P<lng>[-+]?\d+(?:\.\d+)?)\s+(?P<lat>[-+]?\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)
_QID_RE = re.compile(r"\bQ[1-9][0-9]*\b")
_OSM_ID_RE = re.compile(r"\b(node|way|relation)[/:](\d+)\b", re.IGNORECASE)


def _as_float(value: object, *, field_name: str) -> float:
    try:
        if not isinstance(value, int | float | str):
            raise TypeError
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid float") from exc


def _optional_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        if not isinstance(value, int | float | str):
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        if not isinstance(value, int | str):
            raise TypeError
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_string(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, list | tuple):
        for item in value:
            if text := _first_string(item):
                return text
    if isinstance(value, dict):
        for key in ("en", "local", "default", "value"):
            if text := _first_string(value.get(key)):
                return text
        for item in value.values():
            if text := _first_string(item):
                return text
    return None


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _qid_from_value(value: object) -> str | None:
    text = _first_string(value)
    if not text:
        return None
    match = _QID_RE.search(text)
    return match.group(0) if match else None


def _osm_id_from_value(value: object) -> str | None:
    text = _first_string(value)
    if not text:
        return None
    match = _OSM_ID_RE.search(text)
    if not match:
        return None
    return f"{match.group(1).lower()}/{match.group(2)}"


def _source_record(row: dict[str, Any], *datasets: str) -> str | None:
    dataset_names = {dataset.lower() for dataset in datasets}
    sources = row.get("sources")
    if not isinstance(sources, list):
        return None
    for source in sources:
        if not isinstance(source, dict):
            continue
        dataset = str(source.get("dataset") or "").strip().lower()
        if dataset not in dataset_names:
            continue
        record_id = str(source.get("record_id") or "").strip()
        if record_id:
            return record_id
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_string_list(item))
        return out
    return []


def _point_from_geometry(geometry: object) -> tuple[float, float] | None:
    if isinstance(geometry, bytes | bytearray | memoryview):
        return _point_from_wkb(bytes(geometry))
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list | tuple) or len(coordinates) < 2:
        return None
    return (
        _as_float(coordinates[1], field_name="latitude"),
        _as_float(coordinates[0], field_name="longitude"),
    )


def _point_from_wkb(value: bytes) -> tuple[float, float] | None:
    if len(value) < 21:
        return None
    byte_order = value[0]
    endian = "<" if byte_order == 1 else ">" if byte_order == 0 else None
    if endian is None:
        return None
    try:
        geometry_type = struct.unpack(f"{endian}I", value[1:5])[0] & 0xFF
        if geometry_type != 1:
            return None
        lng, lat = struct.unpack(f"{endian}dd", value[5:21])
    except struct.error:
        return None
    return (float(lat), float(lng))


def _point_from_wkt(value: object) -> tuple[float, float] | None:
    text = _first_string(value)
    if not text:
        return None
    match = _WKT_POINT_RE.search(text)
    if match is None:
        return None
    return (float(match.group("lat")), float(match.group("lng")))


def _point_from_bbox(value: object) -> tuple[float, float] | None:
    if isinstance(value, dict):
        min_lng = _optional_float(value.get("xmin") or value.get("minx") or value.get("minLon"))
        max_lng = _optional_float(value.get("xmax") or value.get("maxx") or value.get("maxLon"))
        min_lat = _optional_float(value.get("ymin") or value.get("miny") or value.get("minLat"))
        max_lat = _optional_float(value.get("ymax") or value.get("maxy") or value.get("maxLat"))
    elif isinstance(value, list | tuple) and len(value) >= 4:
        min_lng = _optional_float(value[0])
        min_lat = _optional_float(value[1])
        max_lng = _optional_float(value[2])
        max_lat = _optional_float(value[3])
    else:
        return None
    if None in {min_lng, max_lng, min_lat, max_lat}:
        return None
    return ((float(min_lat) + float(max_lat)) / 2, (float(min_lng) + float(max_lng)) / 2)


def _format_address(address: object) -> str | None:
    if isinstance(address, str):
        return address.strip() or None
    if not isinstance(address, dict):
        return None
    parts = [
        address.get("freeform"),
        address.get("street"),
        address.get("locality"),
        address.get("region"),
        address.get("postcode"),
        address.get("country"),
    ]
    rendered = ", ".join(str(part).strip() for part in parts if str(part or "").strip())
    return rendered or None


def _population_score(population: int | None) -> float | None:
    if not population or population <= 0:
        return None
    return min(100.0, round((math.log10(population + 1) / 7.0) * 100.0, 2))


def _feature_code_to_subtype(feature_code: str | None) -> str:
    code = (feature_code or "").strip().upper()
    if code == "PCLI":
        return "country"
    if code in {"ADM1", "ADM2", "ADM3", "ADM4"}:
        return "region"
    if code in {"PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPL"}:
        return "city"
    return "location"


def parse_geonames_row(row: str | dict[str, object] | list[str] | tuple[str, ...]) -> SourceRecord:
    if isinstance(row, str):
        mapped: dict[str, object] = dict(
            zip(GEONAMES_COLUMNS, row.rstrip("\n").split("\t"), strict=False)
        )
    elif isinstance(row, list | tuple):
        mapped = dict(zip(GEONAMES_COLUMNS, row, strict=False))
    else:
        mapped = row

    provider_id = str(mapped.get("geonameid") or mapped.get("geoname_id") or "").strip()
    name = str(mapped.get("name") or mapped.get("asciiname") or "").strip()
    if not provider_id or not name:
        raise ValueError("GeoNames row requires geonameid and name")

    lat = _as_float(mapped.get("latitude"), field_name="latitude")
    lng = _as_float(mapped.get("longitude"), field_name="longitude")
    population = _optional_int(mapped.get("population"))
    country_code = str(mapped.get("country code") or mapped.get("country_code") or "").strip().upper()
    subtype = _feature_code_to_subtype(
        str(mapped.get("feature code") or mapped.get("feature_code") or "")
    )
    aliases = dedupe_text(
        _string_list(mapped.get("alternatenames") or mapped.get("alternate_names")),
        exclude=name,
    )
    return SourceRecord(
        provider=Provider.GEONAMES,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        country_code=country_code or None,
        lat=lat,
        lng=lng,
        aliases=aliases,
        provider_url=f"https://www.geonames.org/{provider_id}",
        external_ids={"geonames": provider_id},
        popularity=_population_score(population),
        population=population,
        raw={key: value for key, value in mapped.items() if value not in (None, "")},
    )


def _provider_from_source(value: object) -> Provider:
    normalized = str(value or "").strip().lower()
    if normalized in {"openstreetmap", "osm"}:
        return Provider.OPENSTREETMAP
    if normalized == "overture":
        return Provider.OVERTURE
    if normalized == "wikidata":
        return Provider.WIKIDATA
    if normalized == "geonames":
        return Provider.GEONAMES
    return Provider.GEOJSON


def _category_list(value: object) -> list[str]:
    if isinstance(value, dict):
        out = []
        out.extend(_string_list(value.get("primary")))
        out.extend(_string_list(value.get("alternate")))
        out.extend(_string_list(value.get("categories")))
        return dedupe_text(out)
    return dedupe_text(_string_list(value))


def parse_overture_row(row: dict[str, Any], *, default_country_code: str | None = None) -> SourceRecord:
    properties = _dict_value(row.get("properties")) if "properties" in row else row
    geometry = row.get("geometry") or properties.get("geometry")
    provider_id = str(properties.get("id") or row.get("id") or "").strip()
    names = _dict_value(properties.get("names"))
    name = _first_string(names.get("primary")) or _first_string(properties.get("name"))
    if not provider_id or not name:
        raise ValueError("Overture row requires id and name")

    point = _point_from_geometry(geometry) or _point_from_bbox(properties.get("bbox") or row.get("bbox"))
    if point is None:
        lat = _optional_float(properties.get("lat") or properties.get("latitude"))
        lng = _optional_float(properties.get("lng") or properties.get("lon") or properties.get("longitude"))
        if lat is None or lng is None:
            raise ValueError("Overture row requires point geometry or coordinates")
    else:
        lat, lng = point

    categories = _category_list(properties.get("categories"))
    basic_category = str(properties.get("basic_category") or properties.get("basicCategory") or "").strip()
    subtype = choose_subtype(categories, basic_category or None)
    address = properties.get("address") or properties.get("addresses")
    if isinstance(address, list):
        address = address[0] if address else None
    address_dict = _dict_value(address)
    country_code = (
        str(address_dict.get("country") or properties.get("country") or default_country_code or "")
        .strip()
        .upper()
        or None
    )
    aliases = dedupe_text(_string_list(_dict_value(names.get("common"))), exclude=name)
    confidence = properties.get("confidence")
    source_confidence = float(confidence) if isinstance(confidence, int | float) else None
    website = _first_string(properties.get("websites") or properties.get("website"))
    phone = _first_string(properties.get("phones") or properties.get("phone"))
    external_ids: dict[str, str] = {}
    if qid := (
        _qid_from_value(properties.get("wikidata"))
        or _qid_from_value(properties.get("qid"))
        or _qid_from_value(_source_record(properties, "wikidata"))
    ):
        external_ids["qid"] = qid
    if geonames_id := _first_string(
        properties.get("geonames") or properties.get("geonamesId") or properties.get("geonames_id")
    ):
        external_ids["geonames"] = geonames_id
    if fsq_id := _source_record(properties, "foursquare"):
        external_ids["fsq"] = fsq_id
    if osm_id := _osm_id_from_value(_source_record(properties, "openstreetmap", "osm")):
        external_ids["osm"] = osm_id
    return SourceRecord(
        provider=Provider.OVERTURE,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        lat=float(lat),
        lng=float(lng),
        country_code=country_code,
        aliases=aliases,
        categories=categories,
        address=_format_address(address),
        phone=phone,
        website=website,
        external_ids=external_ids,
        source_confidence=source_confidence,
        popularity=round(source_confidence * 100, 2) if source_confidence is not None else None,
        raw={key: value for key, value in properties.items() if key not in {"geometry"}},
    )


def _binding_value(binding: dict[str, Any], key: str) -> str | None:
    value = binding.get(key)
    if isinstance(value, dict):
        return _first_string(value.get("value"))
    return _first_string(value)


def _qid_from_uri(value: str | None) -> str:
    if not value:
        return ""
    return value.rstrip("/").rsplit("/", 1)[-1]


def parse_wikidata_binding(
    binding: dict[str, Any], *, default_country_code: str | None = None
) -> SourceRecord:
    provider_id = _qid_from_uri(_binding_value(binding, "place") or _binding_value(binding, "item"))
    name = _binding_value(binding, "placeLabel") or _binding_value(binding, "itemLabel")
    point = _point_from_wkt(_binding_value(binding, "coord") or _binding_value(binding, "coordinateLocation"))
    if not provider_id or not name or point is None:
        raise ValueError("Wikidata binding requires entity id, label, and coordinates")
    instance_label = _binding_value(binding, "instanceLabel")
    subtype = choose_subtype([instance_label or ""]) or "tourist_attraction"
    country_code = (_binding_value(binding, "countryCode") or default_country_code or "").strip().upper()
    aliases = dedupe_text(_string_list(_binding_value(binding, "altLabel")), exclude=name)
    geonames_id = _binding_value(binding, "geonames")
    external_ids = {"qid": provider_id}
    if geonames_id:
        external_ids["geonames"] = geonames_id
    return SourceRecord(
        provider=Provider.WIKIDATA,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        lat=point[0],
        lng=point[1],
        country_code=country_code or None,
        aliases=aliases,
        categories=[instance_label] if instance_label else [],
        description=_binding_value(binding, "placeDescription") or _binding_value(binding, "itemDescription"),
        website=_binding_value(binding, "website"),
        provider_url=f"https://www.wikidata.org/wiki/{provider_id}",
        external_ids=external_ids,
        raw={key: value for key, value in binding.items() if value not in (None, "")},
    )


def parse_wikidata_entity(
    entity: dict[str, Any], *, default_country_code: str | None = None
) -> SourceRecord | None:
    provider_id = str(entity.get("id") or "").strip()
    labels = _dict_value(entity.get("labels"))
    claims = _dict_value(entity.get("claims"))
    name = _first_string(labels.get("en")) or _first_string(labels)
    coord_claims = claims.get("P625")
    point = None
    if isinstance(coord_claims, list) and coord_claims:
        value = (
            _dict_value(_dict_value(coord_claims[0].get("mainsnak")).get("datavalue")).get("value")
        )
        if isinstance(value, dict) and "latitude" in value and "longitude" in value:
            point = (float(value["latitude"]), float(value["longitude"]))
    if not provider_id or not name or point is None:
        return None
    aliases: list[str] = []
    for value in _dict_value(entity.get("aliases")).values():
        aliases.extend(_string_list(value))
    subtype = "tourist_attraction"
    return SourceRecord(
        provider=Provider.WIKIDATA,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        lat=point[0],
        lng=point[1],
        country_code=default_country_code,
        aliases=dedupe_text(aliases, exclude=name),
        provider_url=f"https://www.wikidata.org/wiki/{provider_id}",
        external_ids={"qid": provider_id},
        raw=entity,
    )


def _osm_tags(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item).strip() for key, item in value.items() if str(item).strip()}


def _osm_display_name(tags: dict[str, str]) -> str | None:
    return tags.get("name:en") or tags.get("int_name") or tags.get("name")


def _osm_subtype_from_tags(tags: dict[str, str]) -> str | None:
    amenity = tags.get("amenity")
    tourism = tags.get("tourism")
    historic = tags.get("historic")
    leisure = tags.get("leisure")
    boundary = tags.get("boundary")
    natural = tags.get("natural")
    railway = tags.get("railway")
    if amenity in {"restaurant", "bar", "cafe", "pub", "biergarten", "fast_food", "food_court"}:
        return "bar" if amenity in {"pub", "biergarten"} else "restaurant" if amenity in {"fast_food", "food_court"} else amenity
    if amenity in {"theatre", "events_venue", "conference_centre"}:
        return "event_venue"
    if amenity == "place_of_worship":
        return "place_of_worship"
    if tourism in {"hotel", "motel", "guest_house", "resort", "hostel"}:
        return "hotel"
    if tourism in {"museum", "gallery", "attraction", "viewpoint", "zoo", "aquarium", "theme_park"}:
        return "art_gallery" if tourism == "gallery" else "tourist_attraction" if tourism in {"attraction", "viewpoint"} else tourism
    if leisure in {"park", "nature_reserve", "stadium"}:
        return "national_park" if leisure == "nature_reserve" else leisure
    if boundary == "protected_area":
        return "national_park"
    if historic in {"archaeological_site", "castle", "ruins", "monument", "memorial"}:
        return historic
    if natural in {"beach", "peak", "waterfall", "volcano"}:
        return natural
    if railway in {"station", "halt"}:
        return "train_station"
    if tags.get("aeroway") == "aerodrome":
        return "airport"
    if tags.get("place") in {"city", "town", "village", "country", "region", "neighbourhood", "suburb"}:
        place = tags["place"]
        return "neighborhood" if place in {"neighbourhood", "suburb"} else "city" if place in {"town", "village"} else place
    return None


def _osm_categories(tags: dict[str, str]) -> list[str]:
    keys = [
        "amenity",
        "tourism",
        "historic",
        "leisure",
        "boundary",
        "natural",
        "railway",
        "aeroway",
        "place",
    ]
    return [f"{key}={tags[key]}" for key in keys if key in tags]


def _osm_aliases(tags: dict[str, str], *, name: str) -> list[str]:
    aliases: list[str] = []
    for key, value in tags.items():
        if key == "name" or key == "alt_name" or key.startswith("alt_name:") or key.startswith("name:"):
            aliases.extend(_string_list(value))
    return dedupe_text(aliases, exclude=name)


def parse_openstreetmap_element(
    element: dict[str, Any], *, default_country_code: str | None = None
) -> SourceRecord | None:
    tags = _osm_tags(element.get("tags"))
    name = _osm_display_name(tags)
    if not name:
        return None
    subtype = _osm_subtype_from_tags(tags)
    if not subtype:
        return None
    osm_type = str(element.get("type") or element.get("osmType") or "").strip().lower()
    osm_id = str(element.get("id") or element.get("osmId") or "").strip()
    if osm_type not in {"node", "way", "relation"} or not osm_id:
        return None
    center = _dict_value(element.get("center"))
    lat = _optional_float(element.get("lat") or element.get("latitude") or center.get("lat"))
    lng = _optional_float(
        element.get("lng")
        or element.get("lon")
        or element.get("longitude")
        or center.get("lng")
        or center.get("lon")
    )
    if lat is None or lng is None:
        return None
    provider_id = f"{osm_type}/{osm_id}"
    external_ids: dict[str, str] = {"osm": provider_id}
    for key in ("wikidata", "wikipedia"):
        if key == "wikidata" and tags.get(key):
            external_ids["qid"] = tags[key]
        elif tags.get(key):
            external_ids[key] = tags[key]
    country_code = (
        tags.get("addr:country")
        or tags.get("is_in:country_code")
        or default_country_code
        or ""
    ).upper() or None
    return SourceRecord(
        provider=Provider.OPENSTREETMAP,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        lat=lat,
        lng=lng,
        country_code=country_code,
        aliases=_osm_aliases(tags, name=name),
        categories=_osm_categories(tags),
        description=tags.get("description:en") or tags.get("description"),
        phone=tags.get("phone") or tags.get("contact:phone"),
        website=tags.get("website") or tags.get("contact:website") or tags.get("url"),
        provider_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        external_ids=external_ids,
        popularity=95.0 if tags.get("heritage") or tags.get("wikipedia") else None,
        raw={"tags": tags, "osmType": osm_type, "osmId": osm_id},
    )


def parse_geojson_feature(
    feature: dict[str, Any], *, default_country_code: str | None = None
) -> SourceRecord | None:
    properties = _dict_value(feature.get("properties"))
    point = _point_from_geometry(feature.get("geometry"))
    if point is None:
        return None
    name = str(properties.get("name") or properties.get("displayName") or "").strip()
    provider_id = str(properties.get("id") or properties.get("providerId") or "").strip()
    if not name or not provider_id:
        return None
    provider = _provider_from_source(properties.get("source") or properties.get("provider"))
    categories = _category_list(properties.get("categories"))
    subtype = choose_subtype(
        categories,
        str(properties.get("basic_category") or properties.get("basicCategory") or "").strip()
        or None,
    )
    confidence = properties.get("confidence")
    source_confidence = float(confidence) if isinstance(confidence, int | float) else None
    return SourceRecord(
        provider=provider,
        provider_id=provider_id,
        place_type=place_type_from_subtype(subtype),
        subtype=subtype,
        name=name,
        lat=point[0],
        lng=point[1],
        country_code=str(properties.get("countryCode") or default_country_code or "").upper()
        or None,
        aliases=dedupe_text(_string_list(properties.get("aliases")), exclude=name),
        categories=categories,
        description=str(properties.get("description") or "").strip() or None,
        address=_format_address(properties.get("address")),
        phone=str(properties.get("phone") or "").strip() or None,
        website=str(properties.get("website") or "").strip() or None,
        provider_url=str(properties.get("providerUrl") or "").strip() or None,
        source_confidence=source_confidence,
        popularity=round(source_confidence * 100, 2) if source_confidence is not None else None,
        raw={key: value for key, value in properties.items() if value not in (None, "")},
    )


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_geojson_records(path: Path, *, default_country_code: str | None = None) -> Iterator[SourceRecord]:
    with _open_text(path) as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and isinstance(payload.get("features"), list):
        for feature in payload["features"]:
            if isinstance(feature, dict):
                record = parse_geojson_feature(feature, default_country_code=default_country_code)
                if record is not None:
                    yield record
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                record = parse_geojson_feature(item, default_country_code=default_country_code)
                if record is not None:
                    yield record


def iter_jsonl_records(
    path: Path, parser: str, *, default_country_code: str | None = None
) -> Iterator[SourceRecord]:
    with _open_text(path) as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            record = parse_source_row(parser, row, default_country_code=default_country_code)
            if record is not None:
                yield record


def iter_geonames_records(path: Path) -> Iterator[SourceRecord]:
    with _open_text(path) as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield parse_geonames_row(stripped)


def iter_openstreetmap_xml_records(
    path: Path, *, default_country_code: str | None = None
) -> Iterator[SourceRecord]:
    for _event, element in ET.iterparse(path, events=("end",)):
        if element.tag not in {"node", "way", "relation"}:
            continue
        tags = {tag.attrib.get("k", ""): tag.attrib.get("v", "") for tag in element.findall("tag")}
        payload: dict[str, Any] = {
            "type": element.tag,
            "id": element.attrib.get("id"),
            "lat": element.attrib.get("lat"),
            "lon": element.attrib.get("lon"),
            "tags": tags,
        }
        record = parse_openstreetmap_element(payload, default_country_code=default_country_code)
        if record is not None:
            yield record
        element.clear()


def iter_openstreetmap_pbf_records(
    path: Path, *, default_country_code: str | None = None
) -> Iterator[SourceRecord]:
    try:
        import osmium
    except ImportError as exc:
        raise RuntimeError("Install the 'osm' extra to read .osm.pbf files") from exc

    records: list[SourceRecord] = []

    class Handler(osmium.SimpleHandler):  # type: ignore[misc]
        def _handle(self, obj: Any, osm_type: str) -> None:
            tags = {str(tag.k): str(tag.v) for tag in obj.tags}
            lat = lng = None
            if hasattr(obj, "location") and obj.location.valid():
                lat = obj.location.lat
                lng = obj.location.lon
            elif hasattr(obj, "center") and obj.center:
                lat = getattr(obj.center, "lat", None)
                lng = getattr(obj.center, "lon", None)
            record = parse_openstreetmap_element(
                {"type": osm_type, "id": obj.id, "lat": lat, "lon": lng, "tags": tags},
                default_country_code=default_country_code,
            )
            if record is not None:
                records.append(record)

        def node(self, obj: Any) -> None:
            self._handle(obj, "node")

        def way(self, obj: Any) -> None:
            self._handle(obj, "way")

        def relation(self, obj: Any) -> None:
            self._handle(obj, "relation")

    handler = Handler()
    handler.apply_file(str(path), locations=True)
    yield from records


def iter_overture_parquet_records(
    path: Path, *, default_country_code: str | None = None
) -> Iterator[SourceRecord]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("Install the 'parquet' extra to read Parquet inputs") from exc

    with duckdb.connect(database=":memory:") as conn:
        rows = conn.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        columns = [column[0] for column in conn.description]
    for row in rows:
        mapped = dict(zip(columns, row, strict=True))
        yield parse_overture_row(mapped, default_country_code=default_country_code)


def parse_source_row(
    source: str, row: dict[str, Any], *, default_country_code: str | None = None
) -> SourceRecord | None:
    normalized = source.lower().replace("_", "-")
    if normalized in {"openstreetmap", "osm"}:
        return parse_openstreetmap_element(row, default_country_code=default_country_code)
    if normalized == "overture":
        return parse_overture_row(row, default_country_code=default_country_code)
    if normalized == "wikidata":
        return parse_wikidata_binding(row, default_country_code=default_country_code)
    if normalized in {"wikidata-entity", "wikidata-entity-dump"}:
        return parse_wikidata_entity(row, default_country_code=default_country_code)
    if normalized == "geojson":
        return parse_geojson_feature(row, default_country_code=default_country_code)
    raise ValueError(f"Unsupported source: {source}")


def iter_source_records(
    path: str | Path, source: str, *, default_country_code: str | None = None
) -> Iterator[SourceRecord]:
    input_path = Path(path)
    normalized = source.lower().replace("_", "-")
    suffixes = [suffix.lower() for suffix in input_path.suffixes]
    if normalized == "geonames":
        yield from iter_geonames_records(input_path)
    elif normalized in {"geojson", "open-data-geojson"} and ".jsonl" not in suffixes:
        yield from iter_geojson_records(input_path, default_country_code=default_country_code)
    elif normalized in {"openstreetmap", "osm"} and ".pbf" in suffixes:
        yield from iter_openstreetmap_pbf_records(input_path, default_country_code=default_country_code)
    elif normalized in {"openstreetmap", "osm"} and any(suffix in {".osm", ".xml"} for suffix in suffixes):
        yield from iter_openstreetmap_xml_records(input_path, default_country_code=default_country_code)
    elif normalized == "overture" and ".parquet" in suffixes:
        yield from iter_overture_parquet_records(input_path, default_country_code=default_country_code)
    else:
        yield from iter_jsonl_records(input_path, normalized, default_country_code=default_country_code)
