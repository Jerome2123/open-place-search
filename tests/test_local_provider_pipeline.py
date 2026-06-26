from pathlib import Path

import psycopg

from open_place_search.parsers import iter_source_records
from open_place_search.storage import build_search_documents, ingest_records, init_db

DATABASE_URL = "postgresql://open_places:open_places@localhost:5432/open_places"
FIXTURES = Path(__file__).parent / "fixtures"


def _reset_db(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.commit()
    init_db(conn)


def test_provider_fixtures_ingest_dedupe_and_build_current_documents() -> None:
    provider_files = [
        ("geonames", FIXTURES / "geonames.tsv"),
        ("wikidata", FIXTURES / "wikidata.jsonl"),
        ("openstreetmap", FIXTURES / "openstreetmap.jsonl"),
        ("overture", FIXTURES / "overture.jsonl"),
        ("open_data_geojson", FIXTURES / "open_data_geojson.json"),
    ]

    with psycopg.connect(DATABASE_URL) as conn:
        _reset_db(conn)

        imported = 0
        for source, path in provider_files:
            imported += ingest_records(
                conn,
                iter_source_records(path, source, default_country_code="AU"),
                commit_every=1,
            )

        source_count = conn.execute("SELECT count(*) FROM source_records").fetchone()[0]
        place_count = conn.execute("SELECT count(*) FROM places").fetchone()[0]

        assert imported == 5
        assert source_count == 5
        assert place_count == 3

        built = build_search_documents(conn, commit_every=1)
        document_count = conn.execute("SELECT count(*) FROM poi_search_documents").fetchone()[0]
        qvm_document = conn.execute(
            """
            SELECT name, trusted_aliases, scope_ids, primary_scope_id
            FROM poi_search_documents
            WHERE normalized_name = 'queen victoria market'
            """
        ).fetchone()

        assert built == 3
        assert document_count == 3
        assert qvm_document == ("Queen Victoria Market", "QVM Queen Vic Market", [1], 1)
