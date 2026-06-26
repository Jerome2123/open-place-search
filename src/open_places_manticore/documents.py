from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from open_places_manticore.models import NormalizedPlace, PlaceType
from open_places_manticore.taxonomy import category_ids, category_text


def _text_join(values: Iterable[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in sorted(str(item).strip() for item in values if str(item or "").strip()):
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return " ".join(out)


def _alias_terms(name: str, aliases: Iterable[str]) -> str:
    normalized_name = name.casefold()
    return _text_join(alias for alias in aliases if alias.casefold() != normalized_name)


def category_ids_for_record(
    place_type: PlaceType, subtype: str | None, categories: list[str]
) -> list[int]:
    return category_ids(place_type, subtype, categories)


def quality_tier(source_confidence: float | None, popularity: float | None) -> int:
    confidence = source_confidence if source_confidence is not None else 0.75
    score = popularity if popularity is not None else confidence * 100
    if confidence >= 0.95 and score >= 80:
        return 1
    if confidence >= 0.75 or score >= 60:
        return 2
    return 3


def build_search_document(place: NormalizedPlace) -> dict[str, object]:
    rank_score = float(place.popularity if place.popularity is not None else 0.0)
    confidence_score = float(
        place.source_confidence * 100 if place.source_confidence is not None else rank_score
    )
    popularity_score = rank_score + min(max(place.source_count, 1), 10) ** 0.5
    rendered_category_text = category_text(place.categories, place.subtype)
    quality = quality_tier(place.source_confidence, place.popularity)
    scope_id = 1
    return {
        "id": int(place.id),
        "name": place.name,
        "normalized_name": place.normalized_name,
        "trusted_aliases": _alias_terms(place.name, place.aliases),
        "code_aliases": "",
        "weak_aliases": "",
        "category_text": rendered_category_text,
        "category_ids": category_ids_for_record(place.place_type, place.subtype, place.categories),
        "scope_ids": [scope_id],
        "country_scope_id": scope_id,
        "admin1_scope_id": 0,
        "city_scope_id": scope_id,
        "best_scope_id": scope_id,
        "primary_scope_id": scope_id,
        "scope_display_hash": 0,
        "lat": float(place.lat),
        "lng": float(place.lng),
        "h3_r5": 0,
        "h3_r6": 0,
        "h3_r7": 0,
        "place_type": place.place_type.value,
        "subtype": place.subtype or "",
        "provider": place.provider.value,
        "country_code": place.country_code or "",
        "quality_tier": quality,
        "global_search_tier": quality,
        "rank_score": rank_score,
        "popularity_score": popularity_score,
        "global_name_score": rank_score,
        "global_popularity_score": popularity_score,
        "global_category_score": rank_score,
        "category_quality_score": confidence_score,
        "source_quality_score": confidence_score,
        "review_count": 0,
        "saved_count": 0,
        "is_global_autocomplete": quality <= 1,
        "is_global_exact_searchable": quality <= 2,
        "is_global_prefix_searchable": quality <= 2,
        "has_photo": False,
        "has_description": False,
        "flags": 0,
    }


def build_search_document_from_row(row: Mapping[str, Any]) -> dict[str, object]:
    provider_value = str(row.get("provider") or "geojson")
    type_value = str(row.get("place_type") or "generic")
    place = NormalizedPlace(
        id=int(row["id"]),
        canonical_key=str(row.get("canonical_key") or ""),
        name=str(row["name"]),
        normalized_name=str(row.get("normalized_name") or ""),
        place_type=PlaceType(type_value),
        subtype=str(row.get("subtype") or "") or None,
        provider=__import__("open_places_manticore.models", fromlist=["Provider"]).Provider(
            provider_value
        ),
        country_code=str(row.get("country_code") or "") or None,
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        aliases=list(row.get("aliases") or []),
        categories=list(row.get("categories") or []),
        source_count=int(row.get("source_count") or 1),
        source_confidence=(
            float(row["source_confidence"]) if row.get("source_confidence") is not None else None
        ),
        popularity=float(row["popularity"]) if row.get("popularity") is not None else None,
        website=str(row.get("website") or "") or None,
        phone=str(row.get("phone") or "") or None,
    )
    return build_search_document(place)
