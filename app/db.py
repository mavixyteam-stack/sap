"""Database access, schema bootstrap and first-run seeding."""
import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import auth

HERE = Path(__file__).parent
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://sap:sap@localhost:5432/sap")

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=False,
                      kwargs={"row_factory": dict_row}, timeout=30)


@contextmanager
def conn():
    """Transactional connection: commits on success, rolls back on error."""
    with pool.connection() as c:
        yield c


def init():
    """Open the pool (retrying while Postgres boots), apply schema, seed once."""
    pool.open(wait=False)
    last = None
    for _ in range(60):
        try:
            with conn() as c:
                c.execute("SELECT 1")
            break
        except Exception as e:  # database container still starting
            last = e
            time.sleep(1)
    else:
        raise RuntimeError("Database not reachable: %s" % last)

    with conn() as c:
        c.execute("SELECT pg_advisory_xact_lock(7305001)")  # one worker migrates at a time
        c.execute((HERE / "schema.sql").read_text())
        seed(c)
        import_catalogue(c)
        bootstrap_admin(c)


def get_setting(c, key, default=None):
    r = c.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(c, key, value):
    c.execute("INSERT INTO settings(key,value) VALUES(%s,%s) "
              "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (key, Jsonb(value)))


def secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    with conn() as c:
        v = get_setting(c, "secret_key")
        if not v:
            v = secrets.token_hex(32)
            set_setting(c, "secret_key", v)
        return v


def bootstrap_admin(c):
    if c.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone():
        return
    email = os.environ.get("ADMIN_EMAIL", "admin@saphardware.in").strip().lower()
    pw = os.environ.get("ADMIN_PASSWORD")
    generated = False
    if not pw:
        pw, generated = secrets.token_urlsafe(12), True
    c.execute("INSERT INTO admin_users(email,password_hash) VALUES(%s,%s)", (email, auth.hash_password(pw)))
    if generated:
        print("=" * 60, "\nFIRST RUN: admin login created\n  email:    %s\n  password: %s\n"
              "  (set ADMIN_PASSWORD to choose your own; change it in Admin > Settings)\n" % (email, pw) + "=" * 60,
              flush=True)


def seed(c):
    """Load the original design content the first time the database is empty."""
    if c.execute("SELECT 1 FROM collections LIMIT 1").fetchone():
        return
    d = json.loads((HERE / "seed_data.json").read_text(encoding="utf-8"))
    for col in d["collections"]:
        c.execute("INSERT INTO collections(id,name,blurb,q,mats,scene,position) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                  (col["id"], col["name"], col["blurb"], col["q"], col["mats"], col["scene"], col["position"]))
    for k in d["catalogues"]:
        c.execute("INSERT INTO catalogues(key,name,position) VALUES(%s,%s,%s)", (k["key"], k["name"], k["position"]))
    pages = {"ap": "01–94", "af": "96–225"}
    for k, v in pages.items():
        c.execute("UPDATE catalogues SET pages_label=%s WHERE key=%s", (v, k))
    for i, f in enumerate(d["finishes"]):
        c.execute("INSERT INTO finishes(name,color,position) VALUES(%s,%s,%s)", (f["n"], f["c"], i))
    featured = {pid: i for i, pid in enumerate(d["featured"])}
    for p in d["products"]:
        c.execute(
            "INSERT INTO products(id,code,name,collection_id,catalogue_key,pages,is_new,subs,material,finishes,"
            "image,position,featured,featured_pos) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (p["id"], p["code"], p["name"], p["collection"], p["catalogue"], p["pages"], p["is_new"],
             Jsonb(p["subs"]) if p["subs"] else None, p["material"], p["finishes"], p["image"], p["position"],
             p["id"] in featured, featured.get(p["id"], 0)))
    for i, s in enumerate(d["slides"]):
        c.execute("INSERT INTO slides(title,image,collection_id,position) VALUES(%s,%s,%s,%s)",
                  (s["title"], s["image"], s["collection"], i))
    set_setting(c, "centers", d["centers"])
    set_setting(c, "offices", d["offices"])


def import_catalogue(c):
    """One-time load of the printed catalogue (series order, components, photos) from catalogue_data.json."""
    f = HERE / "catalogue_data.json"
    if not f.exists() or get_setting(c, "catalogue_imported"):
        return
    d = json.loads(f.read_text(encoding="utf-8"))
    for pid, s in d["series"].items():
        r = c.execute("UPDATE products SET series_no=%s, pages=%s, image=%s, gallery=%s, description=%s, "
                      "material=%s, finishes='{}' WHERE id=%s RETURNING id",
                      (s["no"], s["pages"], s["image"], s["gallery"], s["description"], s.get("material", ""), pid)).fetchone()
        if not r:
            continue
        c.execute("DELETE FROM components WHERE product_id=%s", (pid,))
        for i, k in enumerate(s["components"]):
            c.execute("INSERT INTO components(product_id,section,num,code,name,material,image,position) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                      (pid, k["section"], k["num"], k["code"], k["name"], k["material"], k["image"], i))
    set_setting(c, "catalogue_imported", True)
