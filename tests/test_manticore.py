from open_places_manticore.manticore import (
    build_bulk_payload,
    document_from_tsv_values,
    serialize_tsv_row,
    split_sql_statements,
)


def test_bulk_payload_uses_manticore_replace_ndjson() -> None:
    payload = build_bulk_payload(
        [
            (
                42,
                {
                    "name": "Louvre",
                    "trusted_aliases": "Musee du Louvre",
                    "category_ids": [100, 110],
                    "lat": 48.8606,
                    "lng": 2.3376,
                    "is_global_autocomplete": True,
                },
            )
        ],
        index="poi_v1",
    )

    assert payload.endswith("\n")
    assert '"replace":{"index":"poi_v1","id":42' in payload
    assert '"category_ids":[100,110]' in payload


def test_tsv_round_trip_preserves_types() -> None:
    row = {
        "id": 42,
        "name": "Louvre",
        "trusted_aliases": "Musee du Louvre",
        "code_aliases": "",
        "weak_aliases": "",
        "category_text": "museum attraction",
        "category_ids": [100, 110],
        "scope_ids": [1, 2],
        "primary_scope_id": 1,
        "lat": 48.8606,
        "lng": 2.3376,
        "place_type": "attraction",
        "subtype": "museum",
        "provider": "wikidata",
        "country_code": "FR",
        "quality_tier": 1,
        "global_search_tier": 1,
        "rank_score": 98.0,
        "popularity_score": 120.0,
        "review_count": 2,
        "is_global_autocomplete": True,
        "has_photo": False,
    }

    values = serialize_tsv_row(row).split("\t")
    doc_id, document = document_from_tsv_values(values)

    assert doc_id == 42
    assert document["category_ids"] == [100, 110]
    assert document["scope_ids"] == [1, 2]
    assert document["is_global_autocomplete"] is True
    assert document["has_photo"] is False
    assert document["lat"] == 48.8606


def test_split_sql_statements_ignores_comments() -> None:
    assert split_sql_statements("-- comment\nDROP TABLE IF EXISTS poi_v1;\nCREATE TABLE x (a int);") == [
        "DROP TABLE IF EXISTS poi_v1",
        "CREATE TABLE x (a int)",
    ]
