# Current POI Ingest + Manticore Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the standalone local open-place ingestion project so it reflects Traveller's current stage/resolve/`poi_v1` search flow and proves small local samples from every supported open-data provider ingest, dedupe, build Postgres documents, load Manticore, and search successfully.

**Architecture:** Keep the project library-first and app-agnostic, but align its local model with Traveller's current pipeline: provider rows become source records, strong external IDs use `qid`/`geonames`/`osm`/`fsq` keys, dedupe attaches sources to one canonical place, and document loading targets a `poi_v1`-compatible Manticore schema. The local schema remains smaller than Traveller production, but names, fields, and search behavior should match the current operational shape.

**Tech Stack:** Python 3.12, pytest, psycopg 3, Postgres via Docker Compose, Manticore HTTP API via Docker Compose, httpx.

### Task 1: Current-Flow Contract Tests

**Files:**
- Create: `tests/test_current_flow_contracts.py`
- Modify: `src/open_places_manticore/parsers.py`
- Modify: `src/open_places_manticore/storage.py`
- Modify: `src/open_places_manticore/documents.py`
- Modify: `src/open_places_manticore/manticore.py`

**Step 1: Write failing tests**

Add tests that assert:
- OSM rows carrying `wikidata=Q...` expose `external_ids["qid"]`.
- Wikidata rows expose `external_ids["qid"]`.
- GeoNames rows expose `external_ids["geonames"]`.
- Overture `sources` records expose `qid`, `fsq`, and `osm` secondary IDs.
- A current-style document contains `scope_ids`, `primary_scope_id`, global searchability flags, and `poi_v1` column names.

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_current_flow_contracts.py -q`

Expected: failures for old external ID keys and missing `poi_v1` columns.

**Step 3: Implement minimal code**

Normalize external IDs and document columns without adding Traveller-specific runtime dependencies.

**Step 4: Run tests to verify pass**

Run: `pytest tests/test_current_flow_contracts.py -q`

Expected: all tests pass.

### Task 2: Provider Fixture Integration Test

**Files:**
- Create: `tests/fixtures/geonames.tsv`
- Create: `tests/fixtures/overture.jsonl`
- Create: `tests/fixtures/wikidata.jsonl`
- Create: `tests/fixtures/openstreetmap.jsonl`
- Create: `tests/fixtures/open_data_geojson.json`
- Create: `tests/test_local_provider_pipeline.py`

**Step 1: Write failing tests**

Add tests that ingest every fixture into a real local Postgres database, verify rows land in `source_records`, verify cross-provider rows dedupe to fewer canonical `places` than source rows, build `poi_search_documents`, and export/load documents.

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_local_provider_pipeline.py -q`

Expected: failure until the schema/document builder supports the current flow and local database URL wiring.

**Step 3: Implement minimal code**

Add the required schema/document-builder support and fixture parser support.

**Step 4: Run tests to verify pass**

Run: `pytest tests/test_local_provider_pipeline.py -q`

Expected: all provider fixtures ingest and dedupe in Postgres.

### Task 3: Manticore Search Smoke

**Files:**
- Modify: `sql/manticore/places_v1.sql`
- Possibly create: `sql/manticore/poi_v1.sql`
- Modify: `src/open_places_manticore/manticore.py`
- Modify: `src/open_places_manticore/cli.py`
- Create or update: `tests/test_manticore_search_smoke.py`

**Step 1: Write failing tests**

Add a test or scriptable smoke that loads fixture-built documents to Manticore and queries by scope + name/category.

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_manticore_search_smoke.py -q`

Expected: failure until local Manticore loader/query supports `poi_v1`.

**Step 3: Implement minimal code**

Add `poi_v1` schema/columns, a Manticore SQL query helper, and CLI defaults to target `poi_v1`.

**Step 4: Run tests to verify pass**

Run: `pytest tests/test_manticore_search_smoke.py -q`

Expected: loaded documents are searchable by exact name and category within scope.

### Task 4: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`

**Step 1: Update docs**

Describe the current local flow: provider fixtures -> Postgres canonical/source rows -> dedupe -> `poi_search_documents` -> `poi_v1` Manticore -> scoped search.

**Step 2: Run unit tests**

Run: `pytest -q`

Expected: all tests pass.

**Step 3: Run local services**

Run: `docker compose up -d`

Expected: Postgres and Manticore are healthy enough for local commands.

**Step 4: Run local provider ingestion smoke**

Run provider commands for `geonames`, `overture`, `wikidata`, `openstreetmap`, and `open_data_geojson` against fixture files, then build docs, load Manticore, and search.

Expected: every provider reports imported rows, canonical places are deduped, documents load into Manticore, and scoped search returns expected fixture places.
