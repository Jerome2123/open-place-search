# Open Place Search

Local, library-first tooling for public place ingestion, canonical dedupe, compact
Postgres search documents, and `poi_v1` Manticore indexing.

This project is not an API server and it does not include private ranking models or
paid-provider adapters.

## Current Flow

1. Parse small or bulk provider extracts into normalized source records.
2. Upsert every source record into Postgres.
3. Attach records to canonical `places` using conservative dedupe:
   - shared strong external IDs: `qid`, `geonames`, `osm`, `fsq`
   - matching website or phone keys
   - matching normalized name within a type-specific coordinate radius
4. Build `poi_search_documents` with `poi_v1` fields:
   - `trusted_aliases`, `code_aliases`, `weak_aliases`
   - `scope_ids` and `primary_scope_id`
   - searchability flags and quality/popularity scores
5. Export TSV and bulk load Manticore `poi_v1`.
6. Query Manticore with scoped lexical/category search.

## Why Not OpenSearch or Elasticsearch?

OpenSearch and Elasticsearch are excellent general-purpose search platforms, but
they can be overkill for a focused global POI search index. A 100GB+ worldwide POI
dataset usually means planning for replicas, memory headroom, disk watermarks,
snapshots, monitoring, and multi-node operations. On managed search services,
that operational footprint can become the largest cost in the project before the
product has meaningful traffic.

Open Place Search is designed for a narrower, cheaper path:

- Keep canonical place data and durable search documents in Postgres.
- Export compact TSV rows into a purpose-built Manticore full-text index.
- Search inside explicit destination scopes instead of running every query across
  the entire world.
- Tune place ranking with simple, inspectable fields such as aliases, scope IDs,
  popularity, quality tier, category text, and coordinates.
- Run locally or on a small self-managed VM/container before graduating to a
  larger managed cluster.

This is useful when you need:

- Destination-first place search: select a city/region/country, then find POIs
  inside that scope.
- Category browse for restaurants, attractions, hotels, venues, airports, and
  generic points of interest.
- A public-data ingestion pipeline that can merge GeoNames, OSM, Overture,
  Wikidata, and custom GeoJSON records.
- A low-cost search index for side projects, demos, internal tools, or early
  products where managed OpenSearch/Elasticsearch would dominate infrastructure
  spend.
- Transparent ranking logic that can be debugged from Postgres rows and Manticore
  documents.

It is not a drop-in replacement for OpenSearch or Elasticsearch when you need
large-scale log analytics, multi-tenant SaaS search, complex aggregations,
managed snapshots, cross-cluster replication, vector-heavy workloads, or a mature
hosted operations layer. The tradeoff is intentional: less platform surface area,
less operational cost, and a search model shaped around global POI discovery.

## How Is This Different from Nominatim?

[Nominatim](https://nominatim.org/) is a geocoder for OpenStreetMap data. Its core
job is finding locations by name or address and generating addresses from
coordinates. It is the right tool when the primary question is "where is this
address/place?" or "what address is at this lat/lon?"

Open Place Search is a POI discovery index. Its core job is "inside this selected
destination, which places match this query or category?" That difference changes
the data model and ranking strategy:

- Nominatim optimizes for geocoding and reverse geocoding. Open Place Search
  optimizes for destination-scoped POI search and category browse.
- Nominatim is OSM-first. Open Place Search can merge OSM with GeoNames,
  Overture, Wikidata, and custom GeoJSON before building a canonical place index.
- Nominatim can bias results with a `viewbox`, and `bounded=1` can turn the
  viewbox into a hard filter. Open Place Search stores explicit scope IDs on each
  search document, so a city/region/country selection becomes part of the index
  contract rather than only a query-time geographic hint.
- Nominatim special phrases can narrow result types, but the docs warn they are
  not for returning complete object lists in an area. Open Place Search is built
  for scoped candidate retrieval, ranking, and category browse over the indexed
  POI documents you choose to load.
- The public Nominatim service has strict usage limits and does not support
  client-side autocomplete. Open Place Search is meant to be self-hosted and
  adapted for typeahead-style product search.

Use Nominatim when you need address lookup, reverse geocoding, OSM object lookup,
or mature geocoder behavior. Use Open Place Search when you already know the
destination context and need low-cost, inspectable POI search across a merged open
data corpus.

References:

- [Nominatim search API](https://nominatim.org/release-docs/latest/api/Search/)
- [Nominatim reverse geocoding](https://nominatim.org/release-docs/latest/api/Reverse/)
- [Public Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)

## Supported Local Sources

- `geonames`: official tab-delimited dump rows.
- `openstreetmap`: `.osm`, `.xml`, `.osm.pbf`, or Overpass-style JSONL rows.
- `overture`: JSON, JSONL, GeoJSON-style rows, or Parquet.
- `wikidata`: SPARQL JSON binding rows or entity dump JSONL rows.
- `open_data_geojson`: GeoJSON FeatureCollection records.

Provider IDs are preserved, while cross-provider identifiers are normalized onto the
current shared keys. For example, an OSM `wikidata=Q571669` tag and a Wikidata `Q571669`
entity both produce `external_ids["qid"] == "Q571669"`, so they dedupe locally.

## Data Requirements

The repository includes small fixtures under `tests/fixtures/` for verification. Real
indexes require you to download or export source data first:

- GeoNames: download an official tab-delimited city or all-countries dump from
  GeoNames, then ingest it with `--source geonames`.
- OpenStreetMap: use a regional `.osm.pbf` extract, an `.osm`/`.xml` export, or
  Overpass-style JSONL. Install `.[osm]` when reading `.osm.pbf` files.
- Overture Maps: download the places release as Parquet, GeoJSON, JSON, or JSONL.
  Install `.[parquet]` when reading Parquet files.
- Wikidata: export SPARQL JSON bindings or transform an entity dump into JSONL rows.
- Open data GeoJSON: provide a GeoJSON FeatureCollection with names and point
  coordinates, plus any available IDs, categories, websites, or phone numbers.

Large source extracts and generated TSV files should stay outside git; this repo's
`.gitignore` already excludes common `.tsv`, `.osm.pbf`, `.parquet`, and `.dump`
artifacts.

## Live Demo

The live search surface backed by this destination-first place search flow is
<a href="https://at&#108;yss.ai/search">at&#108;yss.ai/search</a>.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,parquet,osm]"

docker compose up -d
```

Default local services:

```text
Postgres:  postgresql://open_places:open_places@localhost:5432/open_places
Manticore: http://127.0.0.1:9308
```

## CLI Workflow

```bash
place-search init-db --database-url postgresql://open_places:open_places@localhost:5432/open_places

place-search ingest --database-url postgresql://open_places:open_places@localhost:5432/open_places --source geonames --path tests/fixtures/geonames.tsv --country-code AU
place-search ingest --database-url postgresql://open_places:open_places@localhost:5432/open_places --source wikidata --path tests/fixtures/wikidata.jsonl --country-code AU
place-search ingest --database-url postgresql://open_places:open_places@localhost:5432/open_places --source openstreetmap --path tests/fixtures/openstreetmap.jsonl --country-code AU
place-search ingest --database-url postgresql://open_places:open_places@localhost:5432/open_places --source overture --path tests/fixtures/overture.jsonl --country-code AU
place-search ingest --database-url postgresql://open_places:open_places@localhost:5432/open_places --source open_data_geojson --path tests/fixtures/open_data_geojson.json --country-code AU

place-search build-documents --database-url postgresql://open_places:open_places@localhost:5432/open_places
place-search export-tsv --database-url postgresql://open_places:open_places@localhost:5432/open_places --out poi_v1.tsv
place-search load-manticore --host 127.0.0.1 --tsv poi_v1.tsv
```

Search smoke:

```bash
curl -X POST "http://127.0.0.1:9308/sql?mode=raw" ^
  --data-binary "SELECT id, name, trusted_aliases FROM poi_v1 WHERE MATCH('Queen') AND scope_ids IN (1) LIMIT 5"
```

## Python API

```python
import psycopg

from open_place_search.parsers import iter_source_records
from open_place_search.storage import init_db, ingest_records, build_search_documents

with psycopg.connect("postgresql://open_places:open_places@localhost:5432/open_places") as conn:
    init_db(conn)
    records = iter_source_records("tests/fixtures/openstreetmap.jsonl", "openstreetmap")
    ingest_records(conn, records)
    build_search_documents(conn)
```

## Verification

Unit and integration tests:

```bash
pytest -q
```

The integration suite expects local Postgres and Manticore to be running from
`docker compose up -d`. It verifies that all fixture providers ingest, source records
dedupe into canonical places, `poi_search_documents` is built, documents load into
`poi_v1`, and Manticore returns scoped search hits.
