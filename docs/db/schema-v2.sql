PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT INTO schema_meta (key, value) VALUES
  ('schema_name', 'cnc_toolbase_v2'),
  ('schema_version', '2.1.0'),
  ('created_for', 'verifiable CNC tool catalog, cutting data, compatibility tree, reviews, favorites, and commerce');

CREATE TABLE manufacturers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  canonical_name TEXT NOT NULL,
  website_url TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tool_categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  parent_id INTEGER REFERENCES tool_categories(id),
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE catalog_tools (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_id TEXT NOT NULL UNIQUE,
  part_number TEXT NOT NULL,
  normalized_part_number TEXT NOT NULL,
  manufacturer_id INTEGER REFERENCES manufacturers(id),
  category_id INTEGER NOT NULL REFERENCES tool_categories(id),
  tool_kind TEXT NOT NULL,
  product_family TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'unknown' CHECK (lifecycle_status IN (
    'active',
    'obsolete',
    'discontinued',
    'unknown'
  )),
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN (
    'unverified',
    'imported',
    'catalog_claim',
    'manufacturer_verified',
    'shop_verified',
    'rejected'
  )),
  name TEXT,
  description TEXT,
  search_text TEXT,
  source_row_id INTEGER,
  source_table TEXT NOT NULL DEFAULT 'tools',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_catalog_tools_category ON catalog_tools(category_id);
CREATE INDEX idx_catalog_tools_manufacturer ON catalog_tools(manufacturer_id);
CREATE INDEX idx_catalog_tools_part_number ON catalog_tools(normalized_part_number);
CREATE INDEX idx_catalog_tools_kind ON catalog_tools(tool_kind);
CREATE INDEX idx_catalog_tools_verification ON catalog_tools(verification_status);

CREATE VIRTUAL TABLE tool_search USING fts5(
  public_id,
  part_number,
  manufacturer,
  category,
  tool_kind,
  product_family,
  description,
  specs,
  tags,
  content=''
);

CREATE TABLE tool_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  alias_type TEXT NOT NULL CHECK (alias_type IN (
    'manufacturer_part_number',
    'ansi',
    'iso',
    'catalog_id',
    'old_id',
    'search_alias'
  )),
  source_note TEXT,
  UNIQUE(tool_id, alias, alias_type)
);

CREATE TABLE sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_key TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL CHECK (source_type IN (
    'manufacturer_product_page',
    'manufacturer_catalog',
    'machine_manual',
    'shop_note',
    'secondary_source',
    'local_file',
    'unknown'
  )),
  title TEXT,
  url TEXT,
  file_name TEXT,
  page_ref TEXT,
  manufacturer_id INTEGER REFERENCES manufacturers(id),
  retrieved_at TEXT,
  notes TEXT
);

CREATE TABLE tool_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL DEFAULT 'row_source' CHECK (evidence_role IN (
    'row_source',
    'primary_source',
    'supporting_source',
    'verification_source',
    'rejection_source'
  )),
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN (
    'unverified',
    'catalog_claim',
    'manufacturer_verified',
    'shop_verified',
    'rejected'
  )),
  notes TEXT,
  UNIQUE(tool_id, source_id, evidence_role)
);

CREATE TABLE tool_specs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  spec_key TEXT NOT NULL,
  spec_label TEXT,
  value_text TEXT,
  value_number REAL,
  unit TEXT,
  value_json TEXT,
  normalized_value TEXT,
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN (
    'unverified',
    'imported',
    'catalog_claim',
    'manufacturer_verified',
    'shop_verified',
    'rejected'
  )),
  confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  notes TEXT,
  UNIQUE(tool_id, spec_key)
);

CREATE INDEX idx_tool_specs_key ON tool_specs(spec_key);
CREATE INDEX idx_tool_specs_value_number ON tool_specs(spec_key, value_number);
CREATE INDEX idx_tool_specs_normalized ON tool_specs(spec_key, normalized_value);

CREATE TABLE tool_spec_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_spec_id INTEGER NOT NULL REFERENCES tool_specs(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  evidence_note TEXT,
  UNIQUE(tool_spec_id, source_id)
);

CREATE TABLE swiss_tool_specs (
  tool_id INTEGER PRIMARY KEY REFERENCES catalog_tools(id) ON DELETE CASCADE,
  component_type TEXT NOT NULL CHECK (component_type IN (
    'machine',
    'shank',
    'module',
    'holder',
    'insert',
    'adapter',
    'spare'
  )),
  mounts_to_public_id TEXT,
  insert_seat TEXT,
  iso_designation TEXT,
  grade TEXT,
  shape TEXT,
  chipbreaker TEXT,
  size TEXT,
  geometry TEXT
);

CREATE TABLE solid_carbide_specs (
  tool_id INTEGER PRIMARY KEY REFERENCES catalog_tools(id) ON DELETE CASCADE,
  solid_carbide_type TEXT CHECK (solid_carbide_type IN (
    'endmill',
    'drill',
    'reamer',
    'threadmill',
    'burr',
    'other'
  )),
  diameter_mm REAL,
  cutting_diameter_mm REAL,
  shank_diameter_mm REAL,
  overall_length_mm REAL,
  flute_length_mm REAL,
  flute_count INTEGER,
  helix_angle_deg REAL,
  coating TEXT,
  material_grade TEXT,
  corner_radius_mm REAL,
  corner_chamfer_mm REAL,
  coolant_through BOOLEAN,
  handedness TEXT CHECK (handedness IN ('right', 'left', 'neutral', 'unknown'))
);

CREATE TABLE compatibility_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  edge_key TEXT NOT NULL UNIQUE,
  subject_tool_id INTEGER REFERENCES catalog_tools(id) ON DELETE CASCADE,
  subject_public_id TEXT NOT NULL,
  relationship TEXT NOT NULL CHECK (relationship IN (
    'mounts_to',
    'accepts_insert',
    'compatible_with_machine',
    'adapts_to',
    'replaces',
    'similar_to'
  )),
  object_tool_id INTEGER REFERENCES catalog_tools(id) ON DELETE CASCADE,
  object_public_id TEXT NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN (
    'unverified',
    'inferred',
    'catalog_claim',
    'manufacturer_verified',
    'shop_verified',
    'rejected'
  )),
  evidence_kind TEXT NOT NULL DEFAULT 'unknown' CHECK (evidence_kind IN (
    'manufacturer_catalog',
    'manufacturer_product_page',
    'machine_manual',
    'shop_note',
    'existing_database',
    'iso_seat_match',
    'unknown'
  )),
  confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  notes TEXT,
  generated_by TEXT NOT NULL DEFAULT 'manual',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compat_subject ON compatibility_edges(subject_public_id);
CREATE INDEX idx_compat_object ON compatibility_edges(object_public_id);
CREATE INDEX idx_compat_relationship ON compatibility_edges(relationship);
CREATE INDEX idx_compat_status ON compatibility_edges(verification_status);

CREATE TABLE compatibility_edge_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  edge_id INTEGER NOT NULL REFERENCES compatibility_edges(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  evidence_note TEXT,
  UNIQUE(edge_id, source_id)
);

CREATE TABLE cutting_data_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  source_part_number TEXT NOT NULL,
  source_grade TEXT,
  source_geometry TEXT,
  source_chipbreaker TEXT,
  source_material_label TEXT,
  iso_material_group TEXT NOT NULL CHECK (iso_material_group IN (
    'P',
    'M',
    'K',
    'N',
    'S',
    'H',
    'O',
    'unknown'
  )),
  material_subgroup TEXT,
  operation_type TEXT NOT NULL DEFAULT 'turning' CHECK (operation_type IN (
    'turning',
    'boring',
    'grooving',
    'parting',
    'threading',
    'drilling',
    'milling',
    'unknown'
  )),
  cut_condition TEXT CHECK (cut_condition IN (
    'finishing',
    'medium',
    'roughing',
    'general',
    'unknown'
  )),
  coolant_condition TEXT CHECK (coolant_condition IN (
    'dry',
    'flood',
    'high_pressure',
    'mql',
    'unknown'
  )),
  surface_speed_min REAL,
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
  extraction_method TEXT NOT NULL DEFAULT 'manual' CHECK (extraction_method IN (
    'manual',
    'pdf_table',
    'manufacturer_page',
    'scripted_import',
    'shop_entry'
  )),
  verification_status TEXT NOT NULL DEFAULT 'proposed' CHECK (verification_status IN (
    'proposed',
    'source_extracted',
    'needs_review',
    'catalog_verified',
    'manufacturer_verified',
    'shop_verified',
    'rejected'
  )),
  reviewer TEXT,
  reviewed_at TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (surface_speed_min IS NULL OR surface_speed_max IS NULL OR surface_speed_min <= surface_speed_max),
  CHECK (feed_min IS NULL OR feed_max IS NULL OR feed_min <= feed_max),
  CHECK (depth_of_cut_min IS NULL OR depth_of_cut_max IS NULL OR depth_of_cut_min <= depth_of_cut_max)
);

CREATE INDEX idx_cutting_data_tool ON cutting_data_profiles(tool_id);
CREATE INDEX idx_cutting_data_source ON cutting_data_profiles(source_id);
CREATE INDEX idx_cutting_data_material ON cutting_data_profiles(iso_material_group, material_subgroup);
CREATE INDEX idx_cutting_data_operation ON cutting_data_profiles(operation_type);
CREATE INDEX idx_cutting_data_status ON cutting_data_profiles(verification_status);

CREATE TABLE cutting_data_profile_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cutting_data_profile_id INTEGER NOT NULL REFERENCES cutting_data_profiles(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  evidence_role TEXT NOT NULL DEFAULT 'primary_source' CHECK (evidence_role IN (
    'primary_source',
    'supporting_source',
    'conversion_check',
    'review_source',
    'rejection_source'
  )),
  evidence_note TEXT,
  UNIQUE(cutting_data_profile_id, source_id, evidence_role)
);

CREATE TABLE inventory_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER REFERENCES catalog_tools(id),
  sku TEXT NOT NULL UNIQUE,
  condition TEXT NOT NULL DEFAULT 'unknown' CHECK (condition IN (
    'new',
    'new_open_box',
    'used',
    'refurbished',
    'unknown'
  )),
  quantity_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
  location_code TEXT,
  cost_cents INTEGER CHECK (cost_cents IS NULL OR cost_cents >= 0),
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
    'draft',
    'active',
    'paused',
    'sold_out',
    'archived'
  )),
  title TEXT NOT NULL,
  description TEXT,
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'USD',
  quantity_available INTEGER NOT NULL DEFAULT 0 CHECK (quantity_available >= 0),
  allow_backorder BOOLEAN NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE listing_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL,
  alt_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  auth_provider TEXT NOT NULL,
  auth_subject TEXT NOT NULL,
  display_name TEXT,
  email TEXT,
  role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN (
    'customer',
    'staff',
    'admin'
  )),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(auth_provider, auth_subject)
);

CREATE TABLE favorite_tools (
  user_id INTEGER NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, tool_id)
);

CREATE TABLE tool_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES user_profiles(id) ON DELETE SET NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  title TEXT,
  body TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending',
    'published',
    'hidden',
    'deleted'
  )),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_order_id TEXT NOT NULL UNIQUE,
  user_id INTEGER REFERENCES user_profiles(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
    'draft',
    'pending_payment',
    'paid',
    'fulfilled',
    'cancelled',
    'refunded'
  )),
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  shipping_cents INTEGER NOT NULL DEFAULT 0,
  tax_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'USD',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  listing_id INTEGER REFERENCES listings(id),
  tool_id INTEGER REFERENCES catalog_tools(id),
  sku TEXT,
  title TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
  line_total_cents INTEGER NOT NULL CHECK (line_total_cents >= 0)
);
