import asyncio
from pathlib import Path

import httpx
import psycopg

from open_place_search.manticore import load_tsv
from open_place_search.parsers import iter_source_records
from open_place_search.storage import (
    build_search_documents,
    export_search_documents_tsv,
    ingest_records,
    init_db,
)

DATABASE_URL = "postgresql://open_places:open_places@localhost:5432/open_places"
FIXTURES = Path(__file__).parent / "fixtures"
MANTICORE_HOST = "127.0.0.1"
MANTICORE_PORT = 9308


def _reset_db(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.commit()
    init_db(conn)


def _build_fixture_tsv(path: Path) -> int:
    provider_files = [
        ("geonames", FIXTURES / "geonames.tsv"),
        ("wikidata", FIXTURES / "wikidata.jsonl"),
        ("openstreetmap", FIXTURES / "openstreetmap.jsonl"),
        ("overture", FIXTURES / "overture.jsonl"),
        ("open_data_geojson", FIXTURES / "open_data_geojson.json"),
    ]
    with psycopg.connect(DATABASE_URL) as conn:
        _reset_db(conn)
        for source, fixture_path in provider_files:
            ingest_records(
                conn,
                iter_source_records(fixture_path, source, default_country_code="AU"),
                commit_every=1,
            )
        build_search_documents(conn, commit_every=1)
        with path.open("w", encoding="utf-8", newline="") as handle:
            return export_search_documents_tsv(conn, handle)


def test_local_fixture_documents_load_and_search_in_manticore(tmp_path: Path) -> None:
    tsv_path = tmp_path / "poi_v1.tsv"
    exported = _build_fixture_tsv(tsv_path)

    loaded = asyncio.run(
        load_tsv(
            host=MANTICORE_HOST,
            port=MANTICORE_PORT,
            tsv_path=tsv_path,
            schema_path=Path("sql/manticore/poi_v1.sql"),
            index="poi_v1",
            batch_size=2,
        )
    )

    response = httpx.post(
        f"http://{MANTICORE_HOST}:{MANTICORE_PORT}/sql?mode=raw",
        content=(
            "SELECT id, name, trusted_aliases FROM poi_v1 "
            "WHERE MATCH('Queen') AND scope_ids IN (1) "
            "ORDER BY id ASC LIMIT 5"
        ),
        headers={"Content-Type": "text/plain"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload[0]["data"] if isinstance(payload, list) else payload["data"]

    assert exported == 3
    assert loaded == 3
    assert rows
    assert rows[0]["name"] == "Queen Victoria Market"
    assert "QVM" in rows[0]["trusted_aliases"]
