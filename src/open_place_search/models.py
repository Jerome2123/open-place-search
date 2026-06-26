from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from open_place_search.normalization import normalize_text, phone_key, website_host


class Provider(enum.StrEnum):
    OPENSTREETMAP = "openstreetmap"
    OVERTURE = "overture"
    WIKIDATA = "wikidata"
    GEONAMES = "geonames"
    GEOJSON = "geojson"


class PlaceType(enum.StrEnum):
    LOCATION = "location"
    ATTRACTION = "attraction"
    DINING = "dining"
    LODGING = "lodging"
    TRANSPORT = "transport"
    VENUE = "venue"
    GENERIC = "generic"


@dataclass(slots=True)
class SourceRecord:
    provider: Provider
    provider_id: str
    place_type: PlaceType
    subtype: str | None
    name: str
    lat: float
    lng: float
    country_code: str | None = None
    aliases: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    provider_url: str | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    source_confidence: float | None = None
    popularity: float | None = None
    population: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_name(self) -> str:
        return normalize_text(self.name)

    @property
    def phone_key(self) -> str | None:
        return phone_key(self.phone)

    @property
    def website_host(self) -> str | None:
        return website_host(self.website)


@dataclass(slots=True)
class NormalizedPlace:
    id: int
    canonical_key: str
    name: str
    normalized_name: str
    place_type: PlaceType
    subtype: str | None
    provider: Provider
    country_code: str | None
    lat: float
    lng: float
    aliases: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    source_count: int = 1
    source_confidence: float | None = None
    popularity: float | None = None
    website: str | None = None
    phone: str | None = None

