-- SAP Hardware CMS schema. Idempotent: safe to run on every start.

CREATE TABLE IF NOT EXISTS admin_users (
  id            SERIAL PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value JSONB NOT NULL
);

-- "Categories" in the admin panel; shown as "Collections" on the website.
CREATE TABLE IF NOT EXISTS collections (
  id         TEXT PRIMARY KEY,               -- url slug, used in products.html?c=<id>
  name       TEXT NOT NULL,
  blurb      TEXT NOT NULL DEFAULT '',
  q          TEXT NOT NULL DEFAULT '',       -- short descriptor used in SEO text
  mats       TEXT[] NOT NULL DEFAULT '{}',   -- materials typical for this collection
  scene      TEXT NOT NULL DEFAULT '',       -- hover / gallery scene image
  position   INT  NOT NULL DEFAULT 0,
  active     BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The two printed catalogues (Aluminium Profile / Architecture Furniture Fittings).
CREATE TABLE IF NOT EXISTS catalogues (
  key         TEXT PRIMARY KEY,              -- 'ap', 'af'
  name        TEXT NOT NULL,
  pages_label TEXT NOT NULL DEFAULT '',
  position    INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS finishes (
  name     TEXT PRIMARY KEY,
  color    TEXT NOT NULL,
  position INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
  id             TEXT PRIMARY KEY,           -- url slug, used in product.html?id=<id>
  code           TEXT NOT NULL,              -- display code, e.g. AP·01
  name           TEXT NOT NULL,
  collection_id  TEXT NOT NULL REFERENCES collections(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  catalogue_key  TEXT NOT NULL REFERENCES catalogues(key) ON UPDATE CASCADE ON DELETE RESTRICT,
  pages          TEXT NOT NULL DEFAULT '',
  is_new         BOOLEAN NOT NULL DEFAULT FALSE,
  subs           JSONB,                      -- [[variant name, page], ...]
  material       TEXT NOT NULL DEFAULT '',
  finishes       TEXT[] NOT NULL DEFAULT '{}',
  image          TEXT NOT NULL DEFAULT '',
  gallery        TEXT[] NOT NULL DEFAULT '{}',
  description    TEXT NOT NULL DEFAULT '',
  position       INT NOT NULL DEFAULT 0,
  active         BOOLEAN NOT NULL DEFAULT TRUE,
  featured       BOOLEAN NOT NULL DEFAULT FALSE,
  featured_pos   INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS products_collection_idx ON products(collection_id);

CREATE TABLE IF NOT EXISTS slides (
  id            SERIAL PRIMARY KEY,
  title         TEXT NOT NULL,
  image         TEXT NOT NULL,
  collection_id TEXT REFERENCES collections(id) ON UPDATE CASCADE ON DELETE SET NULL,
  position      INT NOT NULL DEFAULT 0,
  active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS enquiries (
  id          SERIAL PRIMARY KEY,
  topic       TEXT NOT NULL DEFAULT 'product',
  name        TEXT NOT NULL,
  phone       TEXT NOT NULL,
  email       TEXT NOT NULL DEFAULT '',
  city        TEXT NOT NULL DEFAULT '',
  message     TEXT NOT NULL DEFAULT '',
  items_count INT  NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'new',   -- new | done
  ip          TEXT NOT NULL DEFAULT '',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
