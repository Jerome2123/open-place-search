CREATE TABLE IF NOT EXISTS places (
  id bigserial PRIMARY KEY,
  canonical_key text NOT NULL UNIQUE,
  name text NOT NULL,
  normalized_name text NOT NULL,
  place_type text NOT NULL,
  subtype text,
  provider text NOT NULL,
  country_code text,
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  phone text,
  phone_key text,
  website text,
  website_host text,
  source_confidence double precision,
  popularity double precision,
  source_count integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS places_normalized_name_idx ON places(normalized_name);
CREATE INDEX IF NOT EXISTS places_website_host_idx ON places(website_host);
CREATE INDEX IF NOT EXISTS places_phone_key_idx ON places(phone_key);

CREATE TABLE IF NOT EXISTS source_records (
  id bigserial PRIMARY KEY,
  provider text NOT NULL,
  provider_id text NOT NULL,
  name text NOT NULL,
  normalized_name text NOT NULL,
  place_type text NOT NULL,
  subtype text,
  country_code text,
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  aliases text[] NOT NULL DEFAULT '{}',
  categories text[] NOT NULL DEFAULT '{}',
  description text,
  address text,
  phone text,
  phone_key text,
  website text,
  website_host text,
  provider_url text,
  external_ids jsonb NOT NULL DEFAULT '{}',
  source_confidence double precision,
  popularity double precision,
  population bigint,
  raw jsonb NOT NULL DEFAULT '{}',
  canonical_place_id bigint REFERENCES places(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(provider, provider_id)
);

CREATE INDEX IF NOT EXISTS source_records_external_ids_idx ON source_records USING gin(external_ids);
CREATE INDEX IF NOT EXISTS source_records_canonical_place_id_idx ON source_records(canonical_place_id);

CREATE TABLE IF NOT EXISTS place_sources (
  place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  source_record_id bigint NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
  provider text NOT NULL,
  provider_id text NOT NULL,
  PRIMARY KEY(place_id, source_record_id),
  UNIQUE(provider, provider_id)
);

CREATE TABLE IF NOT EXISTS place_aliases (
  place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  alias text NOT NULL,
  normalized_alias text NOT NULL,
  PRIMARY KEY(place_id, normalized_alias)
);

CREATE TABLE IF NOT EXISTS place_categories (
  place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  category text NOT NULL,
  category_id integer NOT NULL,
  PRIMARY KEY(place_id, category_id, category)
);

CREATE TABLE IF NOT EXISTS poi_search_documents (
  doc_id bigint PRIMARY KEY,
  place_id bigint NOT NULL UNIQUE REFERENCES places(id) ON DELETE CASCADE,
  name text NOT NULL,
  normalized_name text NOT NULL DEFAULT '',
  trusted_aliases text NOT NULL DEFAULT '',
  code_aliases text NOT NULL DEFAULT '',
  weak_aliases text NOT NULL DEFAULT '',
  category_text text NOT NULL DEFAULT '',
  category_ids integer[] NOT NULL DEFAULT '{}',
  scope_ids bigint[] NOT NULL DEFAULT '{}',
  country_scope_id bigint NOT NULL DEFAULT 0,
  admin1_scope_id bigint NOT NULL DEFAULT 0,
  city_scope_id bigint NOT NULL DEFAULT 0,
  best_scope_id bigint NOT NULL DEFAULT 0,
  primary_scope_id bigint NOT NULL DEFAULT 0,
  scope_display_hash bigint NOT NULL DEFAULT 0,
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  h3_r5 bigint NOT NULL DEFAULT 0,
  h3_r6 bigint NOT NULL DEFAULT 0,
  h3_r7 bigint NOT NULL DEFAULT 0,
  place_type text NOT NULL,
  subtype text NOT NULL DEFAULT '',
  provider text NOT NULL,
  country_code text NOT NULL DEFAULT '',
  quality_tier integer NOT NULL,
  global_search_tier integer NOT NULL,
  rank_score double precision NOT NULL DEFAULT 0,
  popularity_score double precision NOT NULL DEFAULT 0,
  global_name_score double precision NOT NULL DEFAULT 0,
  global_popularity_score double precision NOT NULL DEFAULT 0,
  global_category_score double precision NOT NULL DEFAULT 0,
  category_quality_score double precision NOT NULL DEFAULT 0,
  source_quality_score double precision NOT NULL DEFAULT 0,
  review_count integer NOT NULL DEFAULT 0,
  saved_count integer NOT NULL DEFAULT 0,
  is_global_autocomplete boolean NOT NULL DEFAULT false,
  is_global_exact_searchable boolean NOT NULL DEFAULT false,
  is_global_prefix_searchable boolean NOT NULL DEFAULT false,
  has_photo boolean NOT NULL DEFAULT false,
  has_description boolean NOT NULL DEFAULT false,
  flags bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
