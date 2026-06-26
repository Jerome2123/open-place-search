from open_place_search.models import PlaceType, Provider, SourceRecord
from open_place_search.storage import choose_canonical_match, source_record_params


def _record(**overrides: object) -> SourceRecord:
    values = {
        "provider": Provider.WIKIDATA,
        "provider_id": "Q1",
        "place_type": PlaceType.ATTRACTION,
        "subtype": "museum",
        "name": "Example Museum",
        "lat": 51.5,
        "lng": -0.1,
        "country_code": "GB",
        "external_ids": {"qid": "Q1"},
    }
    values.update(overrides)
    return SourceRecord(**values)


def test_choose_canonical_match_prefers_shared_external_id() -> None:
    record = _record(provider=Provider.OPENSTREETMAP, provider_id="way/1")
    candidates = [
        {"id": 10, "place_type": "attraction", "external_ids": {"qid": "Q1"}},
        {"id": 11, "place_type": "attraction", "normalized_name": "example museum"},
    ]

    assert choose_canonical_match(record, candidates) == 10


def test_choose_canonical_match_rejects_ambiguous_name_only_match() -> None:
    record = _record(place_type=PlaceType.DINING, subtype="restaurant", external_ids={})
    candidates = [
        {
            "id": 10,
            "place_type": "lodging",
            "normalized_name": "example museum",
            "lat": 51.5001,
            "lng": -0.1001,
        }
    ]

    assert choose_canonical_match(record, candidates) is None


def test_source_record_params_contains_normalized_match_keys() -> None:
    params = source_record_params(
        _record(phone="+44 20 7946 0999", website="https://www.example.org/path")
    )

    assert params["normalized_name"] == "example museum"
    assert params["phone_key"] == "2079460999"
    assert params["website_host"] == "example.org"
