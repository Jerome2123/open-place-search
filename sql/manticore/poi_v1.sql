DROP TABLE IF EXISTS poi_v1;

CREATE TABLE poi_v1 (
  name text,
  trusted_aliases text,
  code_aliases text,
  weak_aliases text,
  category_text text,

  category_ids multi,
  scope_ids multi,

  country_scope_id bigint,
  admin1_scope_id bigint,
  city_scope_id bigint,
  best_scope_id bigint,
  primary_scope_id bigint,
  scope_display_hash bigint,

  lat float,
  lng float,
  h3_r5 bigint,
  h3_r6 bigint,
  h3_r7 bigint,

  place_type string attribute,
  subtype string attribute,
  provider string attribute,
  country_code string attribute,

  quality_tier integer,
  global_search_tier integer,
  rank_score float,
  popularity_score float,
  global_name_score float,
  global_popularity_score float,
  global_category_score float,
  category_quality_score float,
  source_quality_score float,
  review_count integer,
  saved_count integer,
  is_global_autocomplete bool,
  is_global_exact_searchable bool,
  is_global_prefix_searchable bool,
  has_photo bool,
  has_description bool,
  flags bigint
) min_infix_len='2' dict='keywords';
