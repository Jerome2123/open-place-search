from open_place_search.documents import build_search_document, category_ids_for_record
from open_place_search.models import NormalizedPlace, PlaceType, Provider


def test_build_search_document_combines_terms_without_rich_payloads() -> None:
    place = NormalizedPlace(
        id=42,
        canonical_key="wikidata:Q19675",
        name="Louvre Museum",
        normalized_name="louvre museum",
        place_type=PlaceType.ATTRACTION,
        subtype="museum",
        provider=Provider.WIKIDATA,
        country_code="FR",
        lat=48.8606,
        lng=2.3376,
        aliases=["Louvre", "Musee du Louvre"],
        categories=["museum", "tourism=attraction"],
        source_count=2,
        source_confidence=0.98,
        popularity=95.0,
        website="https://www.louvre.fr/",
        phone=None,
    )

    document = build_search_document(place)

    assert document["id"] == 42
    assert document["name"] == "Louvre Museum"
    assert document["trusted_aliases"] == "Louvre Musee du Louvre"
    assert document["category_text"] == "museum tourism attraction"
    assert document["category_ids"] == [100, 110]
    assert document["scope_ids"] == [1]
    assert document["primary_scope_id"] == 1
    assert document["quality_tier"] == 1
    assert document["is_global_autocomplete"] is True
    assert "raw" not in document


def test_category_ids_are_deterministic_and_deduplicated() -> None:
    assert category_ids_for_record(PlaceType.DINING, "bar", ["restaurant", "bar"]) == [200, 210]
