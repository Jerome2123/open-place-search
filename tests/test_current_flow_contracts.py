from open_places_manticore.documents import build_search_document
from open_places_manticore.models import NormalizedPlace, PlaceType, Provider
from open_places_manticore.parsers import (
    parse_geonames_row,
    parse_openstreetmap_element,
    parse_overture_row,
    parse_wikidata_binding,
)


def test_provider_external_ids_use_current_shared_keys() -> None:
    osm = parse_openstreetmap_element(
        {
            "type": "node",
            "id": "101",
            "lat": -37.8076,
            "lon": 144.9568,
            "tags": {
                "name": "Queen Victoria Market",
                "tourism": "attraction",
                "wikidata": "Q571669",
            },
        },
        default_country_code="AU",
    )
    wikidata = parse_wikidata_binding(
        {
            "place": {"value": "http://www.wikidata.org/entity/Q571669"},
            "placeLabel": {"value": "Queen Victoria Market"},
            "coord": {"value": "Point(144.9568 -37.8076)"},
            "instanceLabel": {"value": "market"},
            "countryCode": {"value": "AU"},
            "geonames": {"value": "123456"},
        }
    )
    geonames = parse_geonames_row(
        "\t".join(
            [
                "2158177",
                "Melbourne",
                "Melbourne",
                "",
                "-37.8136",
                "144.9631",
                "P",
                "PPLA",
                "AU",
                "",
                "07",
                "",
                "",
                "",
                "5078193",
                "",
                "25",
                "Australia/Melbourne",
                "2026-04-01",
            ]
        )
    )

    assert osm is not None
    assert osm.external_ids["qid"] == "Q571669"
    assert wikidata.external_ids["qid"] == "Q571669"
    assert wikidata.external_ids["geonames"] == "123456"
    assert geonames.external_ids["geonames"] == "2158177"


def test_overture_sources_publish_secondary_source_mappings() -> None:
    record = parse_overture_row(
        {
            "id": "overture:place:qvm",
            "names": {"primary": "Queen Victoria Market"},
            "categories": {"primary": "market"},
            "confidence": 0.94,
            "geometry": {"type": "Point", "coordinates": [144.9568, -37.8076]},
            "sources": [
                {"dataset": "wikidata", "record_id": "http://www.wikidata.org/entity/Q571669"},
                {"dataset": "foursquare", "record_id": "4b05874ef964a520828822e3"},
                {"dataset": "openstreetmap", "record_id": "way/42767742"},
            ],
        },
        default_country_code="AU",
    )

    assert record.external_ids["qid"] == "Q571669"
    assert record.external_ids["fsq"] == "4b05874ef964a520828822e3"
    assert record.external_ids["osm"] == "way/42767742"


def test_search_document_uses_current_poi_v1_shape() -> None:
    document = build_search_document(
        NormalizedPlace(
            id=42,
            canonical_key="wikidata:Q571669",
            name="Queen Victoria Market",
            normalized_name="queen victoria market",
            place_type=PlaceType.ATTRACTION,
            subtype="market",
            provider=Provider.WIKIDATA,
            country_code="AU",
            lat=-37.8076,
            lng=144.9568,
            aliases=["Queen Vic Market", "QVM"],
            categories=["market", "tourism=attraction"],
            source_count=3,
            source_confidence=0.98,
            popularity=96.0,
            website="https://qvm.com.au/",
            phone=None,
        )
    )

    assert document["id"] == 42
    assert document["trusted_aliases"] == "QVM Queen Vic Market"
    assert document["scope_ids"] == [1]
    assert document["primary_scope_id"] == 1
    assert document["global_search_tier"] == 1
    assert document["is_global_autocomplete"] is True
    assert document["is_global_exact_searchable"] is True
    assert document["is_global_prefix_searchable"] is True
    assert "aliases" not in document
    assert "name_hash" not in document
