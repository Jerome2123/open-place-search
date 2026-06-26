from open_places_manticore.models import PlaceType, Provider
from open_places_manticore.parsers import (
    parse_geonames_row,
    parse_geojson_feature,
    parse_openstreetmap_element,
    parse_overture_row,
    parse_wikidata_binding,
)


def test_parse_openstreetmap_element_keeps_named_open_poi() -> None:
    record = parse_openstreetmap_element(
        {
            "type": "way",
            "id": "157376572",
            "lat": -13.1631,
            "lon": -72.5450,
            "tags": {
                "name": "Ciudadela de Machu Picchu",
                "name:en": "Machu Picchu",
                "tourism": "attraction",
                "historic": "archaeological_site",
                "heritage": "1",
                "wikidata": "Q676203",
                "website": "https://www.machupicchu.gob.pe/",
            },
        },
        default_country_code="PE",
    )

    assert record is not None
    assert record.provider == Provider.OPENSTREETMAP
    assert record.provider_id == "way/157376572"
    assert record.place_type == PlaceType.ATTRACTION
    assert record.subtype == "tourist_attraction"
    assert record.name == "Machu Picchu"
    assert "Ciudadela de Machu Picchu" in record.aliases
    assert record.external_ids["qid"] == "Q676203"
    assert record.external_ids["osm"] == "way/157376572"


def test_parse_openstreetmap_element_drops_low_signal_features() -> None:
    assert (
        parse_openstreetmap_element(
            {
                "type": "node",
                "id": "tree-1",
                "lat": 48.858,
                "lon": 2.294,
                "tags": {"natural": "tree", "species": "Platanus"},
            }
        )
        is None
    )


def test_parse_overture_row_maps_nested_place_shape() -> None:
    record = parse_overture_row(
        {
            "type": "Feature",
            "id": "overture:place:bar-margaux",
            "properties": {
                "id": "overture:place:bar-margaux",
                "names": {
                    "primary": "Bar Margaux",
                    "common": {"en": "Bar Margaux", "fr": "Margaux Melbourne"},
                },
                "categories": {
                    "primary": "bar",
                    "alternate": ["restaurant", "french_restaurant"],
                },
                "confidence": 0.93,
                "websites": ["https://www.barmargaux.com.au/"],
                "phones": ["+61 3 9650 0088"],
                "addresses": [
                    {
                        "freeform": "111 Lonsdale Street",
                        "locality": "Melbourne",
                        "region": "VIC",
                        "country": "AU",
                    }
                ],
            },
            "geometry": {"type": "Point", "coordinates": [144.9682, -37.8104]},
        },
        default_country_code="ZZ",
    )

    assert record.provider == Provider.OVERTURE
    assert record.place_type == PlaceType.DINING
    assert record.subtype == "bar"
    assert record.country_code == "AU"
    assert record.aliases == ["Margaux Melbourne"]
    assert record.source_confidence == 0.93


def test_parse_geonames_row_maps_official_dump_columns() -> None:
    line = "\t".join(
        [
            "2158177",
            "Melbourne",
            "Melbourne",
            "Melbourne City,Naarm",
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

    record = parse_geonames_row(line)

    assert record.provider == Provider.GEONAMES
    assert record.provider_id == "2158177"
    assert record.place_type == PlaceType.LOCATION
    assert record.subtype == "city"
    assert record.population == 5_078_193
    assert record.aliases == ["Melbourne City", "Naarm"]


def test_parse_wikidata_binding_maps_sparql_result() -> None:
    record = parse_wikidata_binding(
        {
            "place": {"type": "uri", "value": "http://www.wikidata.org/entity/Q571669"},
            "placeLabel": {"type": "literal", "value": "Queen Victoria Market"},
            "placeDescription": {"type": "literal", "value": "market in Melbourne, Australia"},
            "coord": {
                "datatype": "http://www.opengis.net/ont/geosparql#wktLiteral",
                "type": "literal",
                "value": "Point(144.9568 -37.8076)",
            },
            "instanceLabel": {"type": "literal", "value": "market"},
            "countryCode": {"type": "literal", "value": "AU"},
            "website": {"type": "uri", "value": "https://qvm.com.au/"},
            "altLabel": {"type": "literal", "value": "Queen Vic Market, QVM"},
            "geonames": {"type": "literal", "value": "123456"},
        }
    )

    assert record.provider == Provider.WIKIDATA
    assert record.provider_id == "Q571669"
    assert record.place_type == PlaceType.ATTRACTION
    assert record.subtype == "market"
    assert record.lat == -37.8076
    assert record.lng == 144.9568
    assert record.external_ids["geonames"] == "123456"


def test_parse_geojson_feature_maps_generic_open_record() -> None:
    record = parse_geojson_feature(
        {
            "type": "Feature",
            "properties": {
                "source": "geojson",
                "id": "sample-1",
                "name": "Example Museum",
                "categories": ["museum", "tourist_attraction"],
                "aliases": ["Example Gallery"],
                "countryCode": "GB",
            },
            "geometry": {"type": "Point", "coordinates": [-0.1, 51.5]},
        }
    )

    assert record is not None
    assert record.provider == Provider.GEOJSON
    assert record.place_type == PlaceType.ATTRACTION
    assert record.aliases == ["Example Gallery"]
