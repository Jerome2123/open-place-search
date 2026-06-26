from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TextIO

from open_place_search.documents import build_search_document
from open_place_search.manticore import serialize_tsv_row
from open_place_search.models import NormalizedPlace, PlaceType, Provider, SourceRecord
from open_place_search.normalization import canonical_key, normalize_text
from open_place_search.normalization import phone_key as normalized_phone_key
from open_place_search.normalization import website_host as normalized_website_host
from open_place_search.taxonomy import category_ids, type_compatible

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = PACKAGE_ROOT / "sql" / "postgres_schema.sql"

STRONG_EXTERNAL_ID_KEYS = {"qid", "geonames", "osm", "fsq"}


def source_record_params(record: SourceRecord) -> dict[str, object]:
    return {
        "provider": record.provider.value,
        "provider_id": record.provider_id,
        "name": record.name,
        "normalized_name": record.normalized_name,
        "place_type": record.place_type.value,
        "subtype": record.subtype,
        "country_code": record.country_code,
        "lat": record.lat,
        "lng": record.lng,
        "aliases": record.aliases,
        "categories": record.categories,
        "description": record.description,
        "address": record.address,
        "phone": record.phone,
        "phone_key": normalized_phone_key(record.phone),
        "website": record.website,
        "website_host": normalized_website_host(record.website),
        "provider_url": record.provider_url,
        "external_ids": record.external_ids,
        "source_confidence": record.source_confidence,
        "popularity": record.popularity,
        "population": record.population,
        "raw": record.raw,
    }


def _candidate_place_type(candidate: Mapping[str, object]) -> PlaceType:
    value = str(candidate.get("place_type") or candidate.get("placeType") or "generic")
    try:
        return PlaceType(value)
    except ValueError:
        return PlaceType.GENERIC


def _shared_external_id(record: SourceRecord, candidate: Mapping[str, object]) -> bool:
    candidate_ids = candidate.get("external_ids") or {}
    if not isinstance(candidate_ids, Mapping):
        return False
    for key, value in record.external_ids.items():
        if key in STRONG_EXTERNAL_ID_KEYS and str(candidate_ids.get(key) or "") == str(value):
            return True
    return False


def _distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_m = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _max_name_coordinate_distance(record: SourceRecord) -> float:
    if record.place_type == PlaceType.LOCATION:
        return 25_000
    if record.place_type == PlaceType.TRANSPORT:
        return 3_000
    if record.place_type in {PlaceType.DINING, PlaceType.LODGING, PlaceType.VENUE}:
        return 250
    return 750


def choose_canonical_match(
    record: SourceRecord, candidates: Iterable[Mapping[str, object]]
) -> int | None:
    """Choose an existing place id for a record using conservative merge signals."""
    candidate_list = list(candidates)
    compatible = [
        candidate
        for candidate in candidate_list
        if type_compatible(record.place_type, _candidate_place_type(candidate))
    ]
    for candidate in compatible:
        if _shared_external_id(record, candidate):
            return int(candidate["id"])

    for candidate in compatible:
        if record.website_host and candidate.get("website_host") == record.website_host:
            return int(candidate["id"])
        if record.phone_key and candidate.get("phone_key") == record.phone_key:
            return int(candidate["id"])

    for candidate in compatible:
        if str(candidate.get("normalized_name") or "") != record.normalized_name:
            continue
        candidate_lat = candidate.get("lat")
        candidate_lng = candidate.get("lng")
        if candidate_lat is None or candidate_lng is None:
            continue
        distance = _distance_meters(
            record.lat,
            record.lng,
            float(candidate_lat),
            float(candidate_lng),
        )
        if distance <= _max_name_coordinate_distance(record):
            return int(candidate["id"])
    return None


def init_db(conn: Any, *, schema_path: Path | None = None) -> None:
    schema = (schema_path or DEFAULT_SCHEMA_PATH).read_text(encoding="utf-8")
    conn.execute(schema)
    conn.commit()


def _jsonb(value: object) -> object:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def upsert_source_record(conn: Any, record: SourceRecord) -> int:
    params = source_record_params(record)
    params["external_ids"] = _jsonb(params["external_ids"])
    params["raw"] = _jsonb(params["raw"])
    row = conn.execute(
        """
        INSERT INTO source_records (
          provider, provider_id, name, normalized_name, place_type, subtype, country_code,
          lat, lng, aliases, categories, description, address, phone, phone_key, website,
          website_host, provider_url, external_ids, source_confidence, popularity, population, raw
        )
        VALUES (
          %(provider)s, %(provider_id)s, %(name)s, %(normalized_name)s, %(place_type)s,
          %(subtype)s, %(country_code)s, %(lat)s, %(lng)s, %(aliases)s, %(categories)s,
          %(description)s, %(address)s, %(phone)s, %(phone_key)s, %(website)s,
          %(website_host)s, %(provider_url)s, %(external_ids)s, %(source_confidence)s,
          %(popularity)s, %(population)s, %(raw)s
        )
        ON CONFLICT(provider, provider_id) DO UPDATE SET
          name = EXCLUDED.name,
          normalized_name = EXCLUDED.normalized_name,
          place_type = EXCLUDED.place_type,
          subtype = EXCLUDED.subtype,
          country_code = EXCLUDED.country_code,
          lat = EXCLUDED.lat,
          lng = EXCLUDED.lng,
          aliases = EXCLUDED.aliases,
          categories = EXCLUDED.categories,
          description = EXCLUDED.description,
          address = EXCLUDED.address,
          phone = EXCLUDED.phone,
          phone_key = EXCLUDED.phone_key,
          website = EXCLUDED.website,
          website_host = EXCLUDED.website_host,
          provider_url = EXCLUDED.provider_url,
          external_ids = EXCLUDED.external_ids,
          source_confidence = EXCLUDED.source_confidence,
          popularity = EXCLUDED.popularity,
          population = EXCLUDED.population,
          raw = EXCLUDED.raw,
          updated_at = now()
        RETURNING id
        """,
        params,
    ).fetchone()
    return int(row[0])


def load_match_candidates(conn: Any, record: SourceRecord) -> list[dict[str, object]]:
    params = {
        "normalized_name": record.normalized_name,
        "website_host": record.website_host,
        "phone_key": record.phone_key,
        "lat_min": record.lat - 0.25,
        "lat_max": record.lat + 0.25,
        "lng_min": record.lng - 0.25,
        "lng_max": record.lng + 0.25,
    }
    rows = conn.execute(
        """
        SELECT
          p.id,
          p.normalized_name,
          p.place_type,
          p.lat,
          p.lng,
          p.website_host,
          p.phone_key,
          COALESCE(
            jsonb_object_agg(ids.key, ids.value) FILTER (WHERE ids.key IS NOT NULL),
            '{}'::jsonb
          ) AS external_ids
        FROM places AS p
        LEFT JOIN source_records AS sr ON sr.canonical_place_id = p.id
        LEFT JOIN LATERAL jsonb_each_text(sr.external_ids) AS ids(key, value) ON true
        WHERE p.normalized_name = %(normalized_name)s
           OR (CAST(%(website_host)s AS text) IS NOT NULL AND p.website_host = %(website_host)s)
           OR (CAST(%(phone_key)s AS text) IS NOT NULL AND p.phone_key = %(phone_key)s)
           OR (
             p.lat BETWEEN %(lat_min)s AND %(lat_max)s
             AND p.lng BETWEEN %(lng_min)s AND %(lng_max)s
           )
        GROUP BY p.id
        LIMIT 200
        """,
        params,
    ).fetchall()
    return [
        {
            "id": row[0],
            "normalized_name": row[1],
            "place_type": row[2],
            "lat": row[3],
            "lng": row[4],
            "website_host": row[5],
            "phone_key": row[6],
            "external_ids": row[7] or {},
        }
        for row in rows
    ]


def create_place(conn: Any, record: SourceRecord) -> int:
    row = conn.execute(
        """
        INSERT INTO places (
          canonical_key, name, normalized_name, place_type, subtype, provider, country_code,
          lat, lng, phone, phone_key, website, website_host, source_confidence, popularity,
          source_count
        )
        VALUES (
          %(canonical_key)s, %(name)s, %(normalized_name)s, %(place_type)s, %(subtype)s,
          %(provider)s, %(country_code)s, %(lat)s, %(lng)s, %(phone)s, %(phone_key)s,
          %(website)s, %(website_host)s, %(source_confidence)s, %(popularity)s, 1
        )
        RETURNING id
        """,
        {
            **source_record_params(record),
            "canonical_key": canonical_key(record.provider.value, record.provider_id),
        },
    ).fetchone()
    return int(row[0])


def update_place_from_record(conn: Any, place_id: int, record: SourceRecord) -> None:
    conn.execute(
        """
        UPDATE places
        SET
          source_count = source_count + 1,
          source_confidence = GREATEST(
            COALESCE(source_confidence, 0),
            COALESCE(%(source_confidence)s, 0)
          ),
          popularity = GREATEST(COALESCE(popularity, 0), COALESCE(%(popularity)s, 0)),
          phone = COALESCE(phone, %(phone)s),
          phone_key = COALESCE(phone_key, %(phone_key)s),
          website = COALESCE(website, %(website)s),
          website_host = COALESCE(website_host, %(website_host)s),
          updated_at = now()
        WHERE id = %(place_id)s
        """,
        {**source_record_params(record), "place_id": place_id},
    )


def link_source_record(conn: Any, *, place_id: int, source_record_id: int, record: SourceRecord) -> None:
    conn.execute(
        """
        UPDATE source_records SET canonical_place_id = %(place_id)s WHERE id = %(source_record_id)s
        """,
        {"place_id": place_id, "source_record_id": source_record_id},
    )
    conn.execute(
        """
        INSERT INTO place_sources(place_id, source_record_id, provider, provider_id)
        VALUES (%(place_id)s, %(source_record_id)s, %(provider)s, %(provider_id)s)
        ON CONFLICT(provider, provider_id) DO UPDATE SET
          place_id = EXCLUDED.place_id,
          source_record_id = EXCLUDED.source_record_id
        """,
        {
            "place_id": place_id,
            "source_record_id": source_record_id,
            "provider": record.provider.value,
            "provider_id": record.provider_id,
        },
    )


def upsert_place_terms(conn: Any, place_id: int, record: SourceRecord) -> None:
    for alias in [record.name, *record.aliases]:
        normalized_alias = normalize_text(alias)
        if not normalized_alias:
            continue
        conn.execute(
            """
            INSERT INTO place_aliases(place_id, alias, normalized_alias)
            VALUES (%(place_id)s, %(alias)s, %(normalized_alias)s)
            ON CONFLICT(place_id, normalized_alias) DO UPDATE SET alias = EXCLUDED.alias
            """,
            {"place_id": place_id, "alias": alias, "normalized_alias": normalized_alias},
        )
    for category_id, category in zip(
        category_ids(record.place_type, record.subtype, record.categories),
        [record.subtype or record.place_type.value, *record.categories],
        strict=False,
    ):
        conn.execute(
            """
            INSERT INTO place_categories(place_id, category, category_id)
            VALUES (%(place_id)s, %(category)s, %(category_id)s)
            ON CONFLICT(place_id, category_id, category) DO NOTHING
            """,
            {"place_id": place_id, "category": category, "category_id": category_id},
        )


def upsert_record(conn: Any, record: SourceRecord) -> int:
    source_record_id = upsert_source_record(conn, record)
    candidates = load_match_candidates(conn, record)
    place_id = choose_canonical_match(record, candidates)
    if place_id is None:
        place_id = create_place(conn, record)
    else:
        update_place_from_record(conn, place_id, record)
    link_source_record(conn, place_id=place_id, source_record_id=source_record_id, record=record)
    upsert_place_terms(conn, place_id, record)
    return place_id


def ingest_records(conn: Any, records: Iterable[SourceRecord], *, commit_every: int = 1000) -> int:
    count = 0
    for record in records:
        upsert_record(conn, record)
        count += 1
        if commit_every and count % commit_every == 0:
            conn.commit()
    conn.commit()
    return count


def iter_normalized_places(conn: Any) -> Iterable[NormalizedPlace]:
    rows = conn.execute(
        """
        SELECT
          p.id, p.canonical_key, p.name, p.normalized_name, p.place_type, p.subtype,
          p.provider, p.country_code, p.lat, p.lng, p.source_count, p.source_confidence,
          p.popularity, p.website, p.phone,
          COALESCE(array_agg(DISTINCT pa.alias) FILTER (WHERE pa.alias IS NOT NULL), '{}') AS aliases,
          COALESCE(array_agg(DISTINCT pc.category) FILTER (WHERE pc.category IS NOT NULL), '{}') AS categories
        FROM places AS p
        LEFT JOIN place_aliases AS pa ON pa.place_id = p.id
        LEFT JOIN place_categories AS pc ON pc.place_id = p.id
        GROUP BY p.id
        ORDER BY p.id
        """
    ).fetchall()
    for row in rows:
        yield NormalizedPlace(
            id=int(row[0]),
            canonical_key=str(row[1]),
            name=str(row[2]),
            normalized_name=str(row[3]),
            place_type=PlaceType(str(row[4])),
            subtype=str(row[5] or "") or None,
            provider=Provider(str(row[6])),
            country_code=str(row[7] or "") or None,
            lat=float(row[8]),
            lng=float(row[9]),
            source_count=int(row[10] or 1),
            source_confidence=float(row[11]) if row[11] is not None else None,
            popularity=float(row[12]) if row[12] is not None else None,
            website=str(row[13] or "") or None,
            phone=str(row[14] or "") or None,
            aliases=list(row[15] or []),
            categories=list(row[16] or []),
        )


def upsert_search_document(conn: Any, document: Mapping[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO poi_search_documents (
          doc_id, place_id, name, normalized_name, trusted_aliases, code_aliases,
          weak_aliases, category_text, category_ids, scope_ids, country_scope_id,
          admin1_scope_id, city_scope_id, best_scope_id, primary_scope_id, scope_display_hash,
          lat, lng, h3_r5, h3_r6, h3_r7, place_type, subtype, provider, country_code,
          quality_tier, global_search_tier, rank_score, popularity_score, global_name_score,
          global_popularity_score, global_category_score, category_quality_score,
          source_quality_score, review_count, saved_count, is_global_autocomplete,
          is_global_exact_searchable, is_global_prefix_searchable, has_photo, has_description,
          flags, updated_at
        )
        VALUES (
          %(id)s, %(id)s, %(name)s, %(normalized_name)s, %(trusted_aliases)s, %(code_aliases)s,
          %(weak_aliases)s, %(category_text)s, %(category_ids)s, %(scope_ids)s,
          %(country_scope_id)s, %(admin1_scope_id)s, %(city_scope_id)s, %(best_scope_id)s,
          %(primary_scope_id)s, %(scope_display_hash)s, %(lat)s, %(lng)s, %(h3_r5)s,
          %(h3_r6)s, %(h3_r7)s, %(place_type)s, %(subtype)s, %(provider)s, %(country_code)s,
          %(quality_tier)s, %(global_search_tier)s, %(rank_score)s, %(popularity_score)s,
          %(global_name_score)s, %(global_popularity_score)s, %(global_category_score)s,
          %(category_quality_score)s, %(source_quality_score)s, %(review_count)s,
          %(saved_count)s, %(is_global_autocomplete)s, %(is_global_exact_searchable)s,
          %(is_global_prefix_searchable)s, %(has_photo)s, %(has_description)s, %(flags)s, now()
        )
        ON CONFLICT(place_id) DO UPDATE SET
          name = EXCLUDED.name,
          normalized_name = EXCLUDED.normalized_name,
          trusted_aliases = EXCLUDED.trusted_aliases,
          code_aliases = EXCLUDED.code_aliases,
          weak_aliases = EXCLUDED.weak_aliases,
          category_text = EXCLUDED.category_text,
          category_ids = EXCLUDED.category_ids,
          scope_ids = EXCLUDED.scope_ids,
          country_scope_id = EXCLUDED.country_scope_id,
          admin1_scope_id = EXCLUDED.admin1_scope_id,
          city_scope_id = EXCLUDED.city_scope_id,
          best_scope_id = EXCLUDED.best_scope_id,
          primary_scope_id = EXCLUDED.primary_scope_id,
          scope_display_hash = EXCLUDED.scope_display_hash,
          lat = EXCLUDED.lat,
          lng = EXCLUDED.lng,
          h3_r5 = EXCLUDED.h3_r5,
          h3_r6 = EXCLUDED.h3_r6,
          h3_r7 = EXCLUDED.h3_r7,
          place_type = EXCLUDED.place_type,
          subtype = EXCLUDED.subtype,
          provider = EXCLUDED.provider,
          country_code = EXCLUDED.country_code,
          quality_tier = EXCLUDED.quality_tier,
          global_search_tier = EXCLUDED.global_search_tier,
          rank_score = EXCLUDED.rank_score,
          popularity_score = EXCLUDED.popularity_score,
          global_name_score = EXCLUDED.global_name_score,
          global_popularity_score = EXCLUDED.global_popularity_score,
          global_category_score = EXCLUDED.global_category_score,
          category_quality_score = EXCLUDED.category_quality_score,
          source_quality_score = EXCLUDED.source_quality_score,
          review_count = EXCLUDED.review_count,
          saved_count = EXCLUDED.saved_count,
          is_global_autocomplete = EXCLUDED.is_global_autocomplete,
          is_global_exact_searchable = EXCLUDED.is_global_exact_searchable,
          is_global_prefix_searchable = EXCLUDED.is_global_prefix_searchable,
          has_photo = EXCLUDED.has_photo,
          has_description = EXCLUDED.has_description,
          flags = EXCLUDED.flags,
          updated_at = now()
        """,
        dict(document),
    )


def build_search_documents(conn: Any, *, commit_every: int = 1000) -> int:
    count = 0
    for place in iter_normalized_places(conn):
        upsert_search_document(conn, build_search_document(place))
        count += 1
        if commit_every and count % commit_every == 0:
            conn.commit()
    conn.commit()
    return count


def export_search_documents_tsv(conn: Any, out: TextIO) -> int:
    cursor = conn.execute("SELECT * FROM poi_search_documents ORDER BY doc_id")
    columns = [column.name if hasattr(column, "name") else str(column) for column in cursor.description]
    rows = cursor.fetchall()
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    for row in rows:
        mapping = dict(zip(columns, row, strict=True))
        values = serialize_tsv_row(mapping).split("\t")
        writer.writerow(values)
    return len(rows)
