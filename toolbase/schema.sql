PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT INTO schema_meta (key, value) VALUES
  ('schema_name', 'cnc_toolbase'),
  ('schema_version', '3.4.0'),
  ('purpose', 'source-backed Swiss CNC tooling catalog and compatibility knowledge base');

CREATE TABLE manufacturers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  website_url TEXT
);

CREATE TABLE manufacturer_aliases (
  alias TEXT PRIMARY KEY COLLATE NOCASE,
  manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id)
);

CREATE TABLE tools (
  id TEXT PRIMARY KEY,
  part_number TEXT NOT NULL,
  normalized_part_number TEXT NOT NULL,
  manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id),
  manufacturer_raw TEXT,
  component_type TEXT NOT NULL CHECK (component_type IN (
    'machine', 'station', 'shank', 'module', 'holder', 'insert', 'adapter', 'spare'
  )),
  family TEXT,
  tool_type TEXT,
  description TEXT NOT NULL,
  size TEXT,
  geometry TEXT,
  insert_seat TEXT,
  iso_designation TEXT,
  grade TEXT,
  shape TEXT,
  chipbreaker TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'unknown' CHECK (lifecycle_status IN (
    'active', 'discontinued', 'obsolete', 'unknown'
  )),
  evidence_status TEXT NOT NULL CHECK (evidence_status IN (
    'unverified', 'legacy_source', 'catalog_source', 'manufacturer_source', 'shop_verified'
  )),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN (
    'pending', 'verified', 'quarantined', 'rejected', 'superseded'
  )),
  quarantine_reason TEXT,
  superseded_by_tool_id TEXT REFERENCES tools(id),
  legacy_mounts_to TEXT,
  legacy_record_json TEXT NOT NULL,
  UNIQUE (manufacturer_id, normalized_part_number)
);

CREATE INDEX idx_tools_part_number ON tools(normalized_part_number);
CREATE INDEX idx_tools_manufacturer ON tools(manufacturer_id);
CREATE INDEX idx_tools_component_type ON tools(component_type);
CREATE INDEX idx_tools_evidence_status ON tools(evidence_status);

CREATE TABLE tool_aliases (
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  alias_type TEXT NOT NULL CHECK (alias_type IN (
    'legacy_id', 'manufacturer_part_number', 'iso', 'ansi', 'search'
  )),
  PRIMARY KEY (tool_id, alias, alias_type)
);

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL CHECK (source_type IN (
    'manufacturer_product_page', 'manufacturer_catalog', 'machine_manual',
    'shop_note', 'secondary_web', 'local_file', 'legacy_reference', 'unknown'
  )),
  title TEXT NOT NULL,
  url TEXT,
  local_path TEXT,
  page_ref TEXT,
  manufacturer_id TEXT REFERENCES manufacturers(id),
  raw_reference TEXT NOT NULL,
  content_sha256 TEXT,
  document_edition TEXT,
  retrieved_at TEXT,
  notes TEXT
);

CREATE INDEX idx_sources_type ON sources(source_type);

CREATE TABLE review_batches (
  id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL UNIQUE,
  proposal_path TEXT NOT NULL,
  proposal_sha256 TEXT NOT NULL,
  review_ledger_path TEXT NOT NULL,
  review_ledger_sha256 TEXT NOT NULL,
  catalog_sha256 TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  row_count INTEGER NOT NULL CHECK (row_count > 0)
);

CREATE TABLE review_batch_sources (
  review_batch_id TEXT NOT NULL REFERENCES review_batches(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN (
    'primary_catalog', 'identity', 'grade_application', 'geometry_parameters',
    'cutting_speed', 'verification'
  )),
  content_sha256 TEXT,
  document_edition TEXT,
  page_ref TEXT,
  PRIMARY KEY (review_batch_id, source_id, evidence_role)
);

CREATE TABLE grades (
  id TEXT PRIMARY KEY,
  manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id),
  code TEXT NOT NULL,
  normalized_code TEXT NOT NULL,
  material_class TEXT,
  coating TEXT,
  description TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'unknown' CHECK (lifecycle_status IN (
    'active', 'discontinued', 'obsolete', 'unknown'
  )),
  evidence_status TEXT NOT NULL DEFAULT 'unverified' CHECK (evidence_status IN (
    'unverified', 'imported', 'catalog_claim', 'manufacturer_claim', 'rejected'
  )),
  verification_status TEXT NOT NULL DEFAULT 'legacy' CHECK (verification_status IN (
    'legacy', 'source_located', 'catalog_verified', 'manufacturer_verified', 'rejected'
  )),
  source_id TEXT REFERENCES sources(id),
  source_page_ref TEXT,
  source_table_ref TEXT,
  review_batch_id TEXT REFERENCES review_batches(id),
  reviewer TEXT,
  reviewed_at TEXT,
  UNIQUE (manufacturer_id, normalized_code)
);

CREATE TABLE grade_aliases (
  grade_id TEXT NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  alias_type TEXT NOT NULL CHECK (alias_type IN (
    'legacy', 'former_code', 'manufacturer_alias', 'search'
  )),
  PRIMARY KEY (grade_id, alias, alias_type)
);

CREATE TABLE tool_grade_options (
  id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  grade_id TEXT NOT NULL REFERENCES grades(id),
  option_kind TEXT NOT NULL CHECK (option_kind IN (
    'exact_order_grade', 'available_grade', 'legacy_claim'
  )),
  full_order_number TEXT,
  availability_status TEXT NOT NULL DEFAULT 'unknown' CHECK (availability_status IN (
    'listed', 'unavailable', 'discontinued', 'unknown'
  )),
  is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
  verification_status TEXT NOT NULL DEFAULT 'legacy' CHECK (verification_status IN (
    'legacy', 'source_located', 'catalog_verified', 'manufacturer_verified', 'rejected'
  )),
  source_id TEXT REFERENCES sources(id),
  source_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT CHECK (extraction_method IN (
    'legacy_import', 'manual', 'pdf_table', 'manufacturer_page', 'scripted_import'
  )),
  review_batch_id TEXT REFERENCES review_batches(id),
  reviewer TEXT,
  reviewed_at TEXT,
  UNIQUE (tool_id, grade_id, option_kind)
);

CREATE INDEX idx_tool_grade_tool ON tool_grade_options(tool_id);
CREATE INDEX idx_tool_grade_grade ON tool_grade_options(grade_id);
CREATE INDEX idx_tool_grade_verification ON tool_grade_options(verification_status);

CREATE TABLE shop_input_batches (
  id TEXT PRIMARY KEY,
  input_path TEXT NOT NULL UNIQUE,
  input_sha256 TEXT NOT NULL,
  recorded_by TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  capture_method TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  row_count INTEGER NOT NULL CHECK (row_count > 0)
);

CREATE TABLE reviewed_tool_tags (
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  review_batch_id TEXT NOT NULL REFERENCES review_batches(id),
  PRIMARY KEY (tool_id, tag)
);

CREATE INDEX idx_reviewed_tool_tags_tool ON reviewed_tool_tags(tool_id);

CREATE TABLE tool_sources (
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL DEFAULT 'row_source' CHECK (evidence_role IN (
    'row_source', 'identity', 'specification', 'compatibility', 'verification'
  )),
  PRIMARY KEY (tool_id, source_id, evidence_role)
);

CREATE TABLE facts (
  id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  fact_key TEXT NOT NULL,
  original_key TEXT NOT NULL,
  value_text TEXT,
  value_number REAL,
  value_boolean INTEGER CHECK (value_boolean IN (0, 1)),
  value_json TEXT,
  unit TEXT,
  evidence_status TEXT NOT NULL CHECK (evidence_status IN (
    'unverified', 'imported', 'catalog_claim', 'manufacturer_claim', 'shop_verified', 'rejected'
  )),
  verification_status TEXT NOT NULL DEFAULT 'legacy' CHECK (verification_status IN (
    'legacy', 'source_located', 'catalog_verified', 'manufacturer_verified',
    'shop_verified', 'rejected'
  )),
  source_id TEXT REFERENCES sources(id),
  source_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT CHECK (extraction_method IN (
    'legacy_import', 'manual', 'pdf_table', 'manufacturer_page',
    'scripted_import', 'shop_entry'
  )),
  review_batch_id TEXT REFERENCES review_batches(id),
  reviewer TEXT,
  reviewed_at TEXT,
  supersedes_fact_id TEXT REFERENCES facts(id),
  is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
  CHECK (
    (value_text IS NOT NULL) + (value_number IS NOT NULL) +
    (value_boolean IS NOT NULL) + (value_json IS NOT NULL) = 1
  )
);

CREATE INDEX idx_facts_tool ON facts(tool_id);
CREATE INDEX idx_facts_key_text ON facts(fact_key, value_text);
CREATE INDEX idx_facts_key_number ON facts(fact_key, value_number);
CREATE INDEX idx_facts_verification ON facts(verification_status);

CREATE TABLE fact_sources (
  fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN (
    'legacy_row_source', 'direct_source', 'verification_source'
  )),
  source_page_ref TEXT,
  source_printed_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT,
  PRIMARY KEY (fact_id, source_id, evidence_role)
);

CREATE TABLE work_material_groups (
  iso_group TEXT PRIMARY KEY CHECK (iso_group IN ('P', 'M', 'K', 'N', 'S', 'H', 'O', 'unknown')),
  name TEXT NOT NULL,
  description TEXT,
  sort_order INTEGER NOT NULL
);

CREATE TABLE tool_material_recommendations (
  id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  grade_id TEXT REFERENCES grades(id),
  iso_group TEXT NOT NULL REFERENCES work_material_groups(iso_group),
  material_subgroup TEXT,
  suitability TEXT NOT NULL DEFAULT 'recommended' CHECK (suitability IN (
    'primary', 'recommended', 'conditional', 'not_recommended'
  )),
  evidence_status TEXT NOT NULL CHECK (evidence_status IN (
    'unverified', 'imported', 'catalog_claim', 'manufacturer_claim', 'shop_verified'
  )),
  verification_status TEXT NOT NULL DEFAULT 'legacy' CHECK (verification_status IN (
    'legacy', 'source_located', 'catalog_verified', 'manufacturer_verified',
    'shop_verified', 'rejected'
  )),
  source_id TEXT REFERENCES sources(id),
  source_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT CHECK (extraction_method IN (
    'legacy_import', 'manual', 'pdf_table', 'manufacturer_page',
    'scripted_import', 'shop_entry'
  )),
  review_batch_id TEXT REFERENCES review_batches(id),
  reviewer TEXT,
  reviewed_at TEXT,
  supersedes_recommendation_id TEXT REFERENCES tool_material_recommendations(id),
  is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
  notes TEXT,
  CHECK (grade_id IS NULL OR length(grade_id) > 0)
);

CREATE INDEX idx_tool_material_tool ON tool_material_recommendations(tool_id);
CREATE INDEX idx_tool_material_group ON tool_material_recommendations(iso_group, suitability);
CREATE INDEX idx_tool_material_verification ON tool_material_recommendations(verification_status);
CREATE UNIQUE INDEX idx_tool_material_current_unique
  ON tool_material_recommendations(
    tool_id, ifnull(grade_id, ''), iso_group, ifnull(material_subgroup, '')
  ) WHERE is_current = 1;

CREATE TABLE tool_material_recommendation_sources (
  recommendation_id TEXT NOT NULL REFERENCES tool_material_recommendations(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN (
    'legacy_row_source', 'direct_source', 'verification_source'
  )),
  source_page_ref TEXT,
  source_printed_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT,
  PRIMARY KEY (recommendation_id, source_id, evidence_role)
);

CREATE TABLE cutting_data_profiles (
  id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  grade_id TEXT REFERENCES grades(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  source_part_number TEXT NOT NULL,
  source_grade TEXT,
  source_geometry TEXT,
  source_chipbreaker TEXT,
  source_material_label TEXT,
  iso_material_group TEXT NOT NULL REFERENCES work_material_groups(iso_group),
  material_subgroup TEXT,
  operation_type TEXT NOT NULL CHECK (operation_type IN (
    'turning', 'boring', 'grooving', 'parting', 'threading',
    'drilling', 'milling', 'reaming', 'unknown'
  )),
  cut_condition TEXT NOT NULL DEFAULT 'unknown' CHECK (cut_condition IN (
    'finishing', 'medium', 'roughing', 'general', 'unknown'
  )),
  coolant_condition TEXT NOT NULL DEFAULT 'unknown' CHECK (coolant_condition IN (
    'dry', 'flood', 'high_pressure', 'mql', 'unknown'
  )),
  surface_speed_min REAL,
  surface_speed_start REAL,
  surface_speed_max REAL,
  surface_speed_unit TEXT CHECK (surface_speed_unit IN ('sfm', 'm_per_min')),
  feed_min REAL,
  feed_max REAL,
  feed_unit TEXT CHECK (feed_unit IN ('ipr', 'mm_per_rev', 'ipt', 'mm_per_tooth', 'mm_per_min')),
  depth_of_cut_min REAL,
  depth_of_cut_max REAL,
  depth_of_cut_unit TEXT CHECK (depth_of_cut_unit IN ('in', 'mm')),
  source_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT NOT NULL CHECK (extraction_method IN (
    'manual', 'pdf_table', 'manufacturer_page', 'scripted_import', 'shop_entry'
  )),
  verification_status TEXT NOT NULL CHECK (verification_status IN (
    'proposed', 'source_extracted', 'needs_review', 'catalog_verified',
    'manufacturer_verified', 'shop_verified', 'rejected'
  )),
  reviewer TEXT,
  reviewed_at TEXT,
  notes TEXT,
  CHECK (surface_speed_min IS NULL OR surface_speed_max IS NULL OR surface_speed_min <= surface_speed_max),
  CHECK (surface_speed_start IS NULL OR surface_speed_min IS NULL OR surface_speed_min <= surface_speed_start),
  CHECK (surface_speed_start IS NULL OR surface_speed_max IS NULL OR surface_speed_start <= surface_speed_max),
  CHECK (feed_min IS NULL OR feed_max IS NULL OR feed_min <= feed_max),
  CHECK (depth_of_cut_min IS NULL OR depth_of_cut_max IS NULL OR depth_of_cut_min <= depth_of_cut_max),
  CHECK (surface_speed_min IS NOT NULL OR surface_speed_max IS NOT NULL),
  CHECK (feed_min IS NOT NULL OR feed_max IS NOT NULL),
  CHECK (depth_of_cut_min IS NOT NULL OR depth_of_cut_max IS NOT NULL)
);

CREATE INDEX idx_cutting_data_tool ON cutting_data_profiles(tool_id);
CREATE INDEX idx_cutting_data_material ON cutting_data_profiles(iso_material_group, material_subgroup);
CREATE INDEX idx_cutting_data_operation ON cutting_data_profiles(operation_type);
CREATE INDEX idx_cutting_data_status ON cutting_data_profiles(verification_status);

CREATE TABLE cutting_data_profile_sources (
  profile_id TEXT NOT NULL REFERENCES cutting_data_profiles(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN (
    'identity', 'grade_application', 'geometry_parameters', 'cutting_speed',
    'verification'
  )),
  source_page_ref TEXT,
  source_printed_page_ref TEXT,
  source_table_ref TEXT,
  source_raw_text TEXT,
  extraction_method TEXT,
  PRIMARY KEY (profile_id, source_id, evidence_role)
);

CREATE TABLE interfaces (
  id TEXT PRIMARY KEY,
  tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  interface_role TEXT NOT NULL CHECK (interface_role IN ('provides', 'requires', 'accepts')),
  interface_type TEXT NOT NULL CHECK (interface_type IN (
    'insert_seat', 'round_shank', 'square_shank', 'modular_connection',
    'machine_station', 'adapter_input', 'adapter_output', 'unknown'
  )),
  designation TEXT,
  shape TEXT,
  size_mm REAL,
  system_name TEXT,
  evidence_status TEXT NOT NULL CHECK (evidence_status IN (
    'unverified', 'imported', 'catalog_claim', 'manufacturer_claim', 'shop_verified'
  )),
  source_id TEXT REFERENCES sources(id),
  notes TEXT
);

CREATE INDEX idx_interfaces_match
  ON interfaces(interface_type, designation, shape, size_mm, system_name);

CREATE TABLE compatibility_claims (
  id TEXT PRIMARY KEY,
  subject_tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL CHECK (relationship IN (
    'station_of', 'accepts_holder', 'accepts_shank', 'accepts_module',
    'mounts_to', 'accepts_insert', 'compatible_with_machine', 'adapts_to',
    'replaces', 'similar_to'
  )),
  object_kind TEXT NOT NULL CHECK (object_kind IN (
    'tool', 'insert_seat', 'machine_model', 'interface', 'external_reference'
  )),
  object_tool_id TEXT REFERENCES tools(id) ON DELETE CASCADE,
  object_value TEXT,
  evidence_status TEXT NOT NULL CHECK (evidence_status IN (
    'unverified', 'imported', 'inferred', 'catalog_claim',
    'manufacturer_claim', 'shop_verified', 'rejected'
  )),
  review_status TEXT NOT NULL CHECK (review_status IN (
    'needs_review', 'accepted', 'rejected', 'superseded'
  )),
  confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  source_id TEXT REFERENCES sources(id),
  evidence_kind TEXT,
  source_page_ref TEXT,
  source_raw_text TEXT,
  notes TEXT,
  generated_by TEXT NOT NULL DEFAULT 'manual',
  suppressed INTEGER NOT NULL DEFAULT 0 CHECK (suppressed IN (0, 1)),
  CHECK (object_tool_id IS NOT NULL OR object_value IS NOT NULL)
);

CREATE INDEX idx_compatibility_subject ON compatibility_claims(subject_tool_id);
CREATE INDEX idx_compatibility_object ON compatibility_claims(object_tool_id);
CREATE INDEX idx_compatibility_relationship ON compatibility_claims(relationship);
CREATE INDEX idx_compatibility_review ON compatibility_claims(review_status, suppressed);

CREATE TABLE compatibility_claim_sources (
  claim_id TEXT NOT NULL REFERENCES compatibility_claims(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN (
    'primary_source', 'subject_record_context', 'object_record_context', 'derivation_input'
  )),
  PRIMARY KEY (claim_id, source_id, evidence_role)
);

CREATE VIEW tool_catalog AS
SELECT
  t.*,
  m.name AS manufacturer
FROM tools t
JOIN manufacturers m ON m.id = t.manufacturer_id;

CREATE VIEW usable_cutting_data AS
SELECT *
FROM cutting_data_profiles
WHERE verification_status IN ('catalog_verified', 'manufacturer_verified');
