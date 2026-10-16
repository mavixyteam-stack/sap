"""SAP Hardware: public site + admin API.

The design files in ./site are served unchanged. Each HTML page gets the live
catalogue (categories, products, hero slides, ...) injected as window.__SAP_DATA
so the existing front-end renders it without any visual change.
"""
import csv
import io
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from PIL import Image, ImageOps
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, db, defaults, mailer, seo

HERE = Path(__file__).parent
SITE_DIR = Path(os.environ.get("SITE_DIR", HERE.parent / "site")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE.parent / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
ADMIN_DIR = HERE / "admin"
MAX_UPLOAD = 15 * 1024 * 1024

login_throttle = auth.Throttle(limit=8, window=600)
enquiry_throttle = auth.Throttle(limit=6, window=600)
_secret = ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _secret
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db.init()
    _secret = db.secret_key()
    yield
    db.pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=800)

# --------------------------------------------------------------------------- public data

_cache = {"at": 0.0, "data": None}


def invalidate():
    _cache["at"] = 0.0


def drive_links(url: str):
    """Google Drive share links -> (view, download). Any other https link is used as-is for both."""
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:export=download&)?id=)([\w-]+)", url or "")
    if m:
        i = m.group(1)
        return "https://drive.google.com/file/d/%s/view" % i, "https://drive.google.com/uc?export=download&id=%s" % i
    return url, url


def clean_url(u: str, field: str = "link") -> str:
    u = (u or "").strip()
    if u and not re.match(r"^https?://[^\s]+$", u, re.I):
        raise HTTPException(400, "The %s must be a full web address starting with https://" % field)
    return u


def get_json(c, key, default):
    v = db.get_setting(c, key, None)
    if isinstance(default, dict):
        return {**default, **(v or {})}
    return v if v is not None else default


def base_url(request: Request, site: dict) -> str:
    env = os.environ.get("SITE_URL", "").strip().rstrip("/")
    return env or (site.get("site_url") or "").strip().rstrip("/") or str(request.base_url).rstrip("/")


def build_public_data():
    if _cache["data"] is not None and time.time() - _cache["at"] < 30:
        return _cache["data"]
    with db.conn() as c:
        site_s = get_json(c, "site", defaults.SITE)
        founder = get_json(c, "founder", defaults.FOUNDER)
        docs = c.execute("SELECT id,title,note,url,cover,catalogue_key FROM documents WHERE active ORDER BY position,id").fetchall()
        cols = c.execute("SELECT * FROM collections WHERE active ORDER BY position, name").fetchall()
        cats = c.execute("SELECT * FROM catalogues ORDER BY position").fetchall()
        fins = c.execute("SELECT * FROM finishes ORDER BY position, name").fetchall()
        prods = c.execute(
            "SELECT p.*, (SELECT count(*) FROM components x WHERE x.product_id=p.id AND x.active) AS n "
            "FROM products p JOIN collections c ON c.id=p.collection_id "
            "WHERE p.active AND c.active ORDER BY p.position, p.id").fetchall()
        slides = c.execute(
            "SELECT s.*, c.name AS col_name FROM slides s LEFT JOIN collections c ON c.id=s.collection_id AND c.active "
            "WHERE s.active ORDER BY s.position, s.id").fetchall()
        feat = c.execute(
            "SELECT p.id FROM products p JOIN collections c ON c.id=p.collection_id "
            "WHERE p.active AND c.active AND p.featured ORDER BY p.featured_pos, p.position").fetchall()
        centers = db.get_setting(c, "centers", [])
        offices = db.get_setting(c, "offices", [])
    counts = {}
    for p in prods:
        counts[p["catalogue_key"]] = counts.get(p["catalogue_key"], 0) + 1
    data = {
        "collections": [{"id": r["id"], "name": r["name"], "blurb": r["blurb"], "q": r["q"],
                         "mats": r["mats"], "scene": r["scene"]} for r in cols],
        "finishes": [{"n": r["name"], "c": r["color"]} for r in fins],
        "catalogues": [{"key": r["key"], "name": r["name"], "pages": r["pages_label"],
                        "count": counts.get(r["key"], 0)} for r in cats],
        "products": [{"id": r["id"], "code": r["code"], "name": r["name"], "col": r["collection_id"],
                      "cat": r["catalogue_key"], "pages": r["pages"], "isNew": r["is_new"], "subs": r["subs"],
                      "mat": r["material"], "fins": r["finishes"], "img": r["image"], "gallery": r["gallery"],
                      "desc": r["description"], "no": r["series_no"], "n": r["n"]} for r in prods],
        "slides": [{"title": r["title"], "img": r["image"], "col": r["collection_id"] if r["col_name"] else "",
                    "label": r["col_name"] or "SAP Hardware"} for r in slides],
        "featured": [r["id"] for r in feat],
        "centers": centers,
        "offices": offices,
        "site": site_s,
        "founder": founder,
        "documents": [{"id": r["id"], "title": r["title"], "note": r["note"], "cover": r["cover"], "cat": r["catalogue_key"],
                       "view": drive_links(r["url"])[0], "download": drive_links(r["url"])[1]} for r in docs],
    }
    _cache.update(at=time.time(), data=data)
    return data


def _inject(html: str, page=None) -> str:
    payload = json.dumps(build_public_data(), ensure_ascii=False).replace("</", "<\\/")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    tag = "<script>window.__SAP_DATA=%s;</script>" % payload
    if page is not None:
        tag += "<script>window.__SAP_PAGE=%s;</script>" % json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    return re.sub(r"<head>", lambda m: "<head>" + tag, html, count=1, flags=re.I)


@app.get("/api/data")
def public_data():
    return JSONResponse(build_public_data(), headers={"Cache-Control": "no-cache"})


@app.get("/api/series/{pid}")
def public_series(pid: str):
    """The components that make up one series, grouped by section, for the product page."""
    with db.conn() as c:
        rows = c.execute("SELECT section, num, code, name, material, image FROM components "
                         "WHERE product_id=%s AND active ORDER BY position, id", (pid,)).fetchall()
    sections, index = [], {}
    for r in rows:
        key = r["section"] or ""
        if key not in index:
            index[key] = {"title": key, "items": []}
            sections.append(index[key])
        index[key]["items"].append({"no": r["num"], "code": r["code"], "name": r["name"], "mat": r["material"], "img": r["image"]})
    return JSONResponse({"total": len(rows), "sections": sections}, headers={"Cache-Control": "public, max-age=60"})


class EnquiryIn(BaseModel):
    topic: str = Field("product", max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=1, max_length=40)
    email: str = Field("", max_length=160)
    city: str = Field("", max_length=120)
    message: str = Field("", max_length=4000)
    items: int = Field(0, ge=0, le=1000)
    product_id: str = Field("", max_length=40)
    website: str = Field("", max_length=200)  # honeypot: real visitors leave this empty


TOPIC = {"product": "Product enquiry", "dist": "Distributorship", "visit": "Display centre visit"}


def _notify(eid: int, row: dict, base: str):
    """Email the SAP team about a new enquiry (in the background; failures never affect the visitor)."""
    with db.conn() as c:
        conf = mailer.effective(get_json(c, "email", defaults.EMAIL), _secret)
    if not conf["host"] or not conf["to"]:
        with db.conn() as c:
            c.execute("UPDATE enquiries SET mail_status=%s WHERE id=%s", ("not configured", eid))
        return
    link = row["page_url"]
    subject = "New enquiry: %s from %s" % (row["product_name"] or TOPIC.get(row["topic"], "Website"), row["name"])
    lines = ["New enquiry from the SAP Hardware website", "", "Type: %s" % TOPIC.get(row["topic"], row["topic"])]
    if row["product_name"]:
        lines += ["Product: %s" % row["product_name"], "Product page: %s" % link]
    lines += ["", "Name: %s" % row["name"], "Phone: %s" % row["phone"], "Email: %s" % (row["email"] or "-"),
              "City: %s" % (row["city"] or "-"), "", "Message:", row["message"] or "-", "",
              "View all enquiries: %s/admin#enquiries" % base]
    esc = seo.esc
    prod = (" — <a href='%s'>%s</a>" % (esc(link), esc(row["product_name"]))) if row["product_name"] else ""
    html = ("<div style='font-family:system-ui,sans-serif;font-size:15px;color:#1C1C1C'>"
            "<h2 style='margin:0 0 12px'>New website enquiry</h2><p><b>%s</b>%s</p>"
            "<table cellpadding='6' style='border-collapse:collapse'>"
            "<tr><td>Name</td><td><b>%s</b></td></tr><tr><td>Phone</td><td><a href='tel:%s'>%s</a></td></tr>"
            "<tr><td>Email</td><td>%s</td></tr><tr><td>City</td><td>%s</td></tr></table>"
            "<p style='white-space:pre-wrap;background:#f4f4f4;padding:12px;border-radius:6px'>%s</p>"
            "<p><a href='%s/admin#enquiries'>Open in admin</a></p></div>") % (
        esc(TOPIC.get(row["topic"], "")), prod, esc(row["name"]), esc(re.sub(r"[^\d+]", "", row["phone"])), esc(row["phone"]),
        esc(row["email"] or "-"), esc(row["city"] or "-"), esc(row["message"] or "-"), esc(base))

    def done(status):
        with db.conn() as c:
            c.execute("UPDATE enquiries SET mail_status=%s WHERE id=%s", (status, eid))
    mailer.send_async(conf, subject, "\n".join(lines), html, row["email"], done)


@app.post("/api/enquiries")
def create_enquiry(e: EnquiryIn, request: Request):
    ip = request.client.host if request.client else ""
    if e.website:  # a bot filled the hidden field: pretend success, store nothing
        return {"ok": True}
    if not enquiry_throttle.hit(ip):
        raise HTTPException(429, "Too many requests. Please try again in a few minutes.")
    topic = e.topic if e.topic in TOPIC else "product"
    pid = pname = page = ""
    data = build_public_data()
    base = base_url(request, data["site"])
    if e.product_id:
        pr = next((x for x in data["products"] if x["id"] == e.product_id), None)
        if pr:
            pid, pname = pr["id"], "%s (%s)" % (pr["name"], pr["code"])
            page = "%s/product.html?id=%s" % (base, pr["id"])
    with db.conn() as c:
        r = c.execute("INSERT INTO enquiries(topic,name,phone,email,city,message,items_count,ip,product_id,product_name,page_url) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                      (topic, e.name.strip(), e.phone.strip(), e.email.strip(), e.city.strip(), e.message.strip(), e.items, ip,
                       pid, pname, page)).fetchone()
    _notify(r["id"], dict(topic=topic, name=e.name.strip(), phone=e.phone.strip(), email=e.email.strip(), city=e.city.strip(),
                          message=e.message.strip(), product_name=pname, page_url=page), base)
    return {"ok": True}


# --------------------------------------------------------------------------- admin auth

admin = APIRouter(prefix="/admin/api")


def current_user(request: Request):
    tok = request.cookies.get(auth.COOKIE)
    uid = auth.read_session(_secret, tok) if tok else None
    if uid is None:
        raise HTTPException(401, "Please sign in")
    if request.method not in ("GET", "HEAD") and request.headers.get("x-requested-with") != "sap-admin":
        raise HTTPException(403, "Bad request origin")
    with db.conn() as c:
        u = c.execute("SELECT id,email FROM admin_users WHERE id=%s", (uid,)).fetchone()
    if not u:
        raise HTTPException(401, "Please sign in")
    return u


class LoginIn(BaseModel):
    email: str
    password: str


@admin.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = request.client.host if request.client else ""
    if not login_throttle.hit(ip):
        raise HTTPException(429, "Too many attempts. Wait 10 minutes and try again.")
    if request.headers.get("x-requested-with") != "sap-admin":
        raise HTTPException(403, "Bad request origin")
    with db.conn() as c:
        u = c.execute("SELECT * FROM admin_users WHERE email=%s", (body.email.strip().lower(),)).fetchone()
    if not u or not auth.verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, auth.make_session(_secret, u["id"]), max_age=auth.SESSION_SECONDS,
                        httponly=True, samesite="lax", secure=secure, path="/")
    return {"email": u["email"]}


@admin.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@admin.get("/me")
def me(u=Depends(current_user)):
    return {"email": u["email"]}


class PasswordIn(BaseModel):
    current: str
    new: str = Field(..., min_length=8, max_length=200)


@admin.post("/password")
def change_password(body: PasswordIn, u=Depends(current_user)):
    with db.conn() as c:
        row = c.execute("SELECT password_hash FROM admin_users WHERE id=%s", (u["id"],)).fetchone()
        if not auth.verify_password(body.current, row["password_hash"]):
            raise HTTPException(400, "Current password is wrong")
        c.execute("UPDATE admin_users SET password_hash=%s WHERE id=%s", (auth.hash_password(body.new), u["id"]))
    return {"ok": True}


# --------------------------------------------------------------------------- helpers

def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "item"


def asset_path(s: str) -> str:
    """Only allow site-relative image paths (uploads or bundled assets)."""
    s = (s or "").strip()
    if not s:
        return ""
    if s.startswith("/"):
        s = s[1:]
    if ".." in s or "://" in s or not re.match(r"^(uploads|assets)/[\w./-]+$", s):
        raise HTTPException(400, "Invalid image path")
    return s


def reorder(c, table: str, ids: List, key: str = "id", pos: str = "position"):
    for i, v in enumerate(ids):
        c.execute("UPDATE %s SET %s=%%s WHERE %s=%%s" % (table, pos, key), (i, v))


# --------------------------------------------------------------------------- summary

@admin.get("/summary")
def summary(u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute(
            "SELECT (SELECT count(*) FROM products) products, (SELECT count(*) FROM products WHERE active) products_live,"
            " (SELECT count(*) FROM collections) collections, (SELECT count(*) FROM collections WHERE active) collections_live,"
            " (SELECT count(*) FROM enquiries WHERE status='new') enquiries_new,"
            " (SELECT count(*) FROM enquiries) enquiries_total").fetchone()
    return r


# --------------------------------------------------------------------------- collections

class CollectionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    blurb: str = Field("", max_length=300)
    q: str = Field("", max_length=200)
    mats: List[str] = []
    scene: str = ""
    active: bool = True


def _col_rows(c):
    return c.execute(
        "SELECT c.*, (SELECT count(*) FROM products p WHERE p.collection_id=c.id) AS product_count "
        "FROM collections c ORDER BY position, name").fetchall()


@admin.get("/collections")
def list_collections(u=Depends(current_user)):
    with db.conn() as c:
        return _col_rows(c)


@admin.post("/collections")
def create_collection(b: CollectionIn, u=Depends(current_user)):
    with db.conn() as c:
        base = slugify(b.name)
        cid, n = base, 2
        while c.execute("SELECT 1 FROM collections WHERE id=%s", (cid,)).fetchone():
            cid, n = "%s-%d" % (base, n), n + 1
        pos = c.execute("SELECT coalesce(max(position),-1)+1 AS p FROM collections").fetchone()["p"]
        c.execute("INSERT INTO collections(id,name,blurb,q,mats,scene,position,active) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                  (cid, b.name.strip(), b.blurb.strip(), b.q.strip(), [m.strip() for m in b.mats if m.strip()],
                   asset_path(b.scene), pos, b.active))
    invalidate()
    return {"id": cid}


@admin.put("/collections/{cid}")
def update_collection(cid: str, b: CollectionIn, u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute("UPDATE collections SET name=%s,blurb=%s,q=%s,mats=%s,scene=%s,active=%s,updated_at=now() "
                      "WHERE id=%s RETURNING id",
                      (b.name.strip(), b.blurb.strip(), b.q.strip(), [m.strip() for m in b.mats if m.strip()],
                       asset_path(b.scene), b.active, cid)).fetchone()
        if not r:
            raise HTTPException(404, "Category not found")
    invalidate()
    return {"ok": True}


@admin.delete("/collections/{cid}")
def delete_collection(cid: str, u=Depends(current_user)):
    with db.conn() as c:
        n = c.execute("SELECT count(*) AS n FROM products WHERE collection_id=%s", (cid,)).fetchone()["n"]
        if n:
            raise HTTPException(409, "This category still has %d product(s). Move or delete them first, "
                                     "or switch the category to Hidden." % n)
        c.execute("DELETE FROM collections WHERE id=%s", (cid,))
    invalidate()
    return {"ok": True}


class IdsIn(BaseModel):
    ids: List[str]


class IntIdsIn(BaseModel):
    ids: List[int]


@admin.post("/collections/reorder")
def reorder_collections(b: IdsIn, u=Depends(current_user)):
    with db.conn() as c:
        reorder(c, "collections", b.ids)
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- catalogues & finishes

class CatalogueIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    pages_label: str = Field("", max_length=40)


@admin.get("/catalogues")
def list_catalogues(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT * FROM catalogues ORDER BY position").fetchall()


@admin.put("/catalogues/{key}")
def update_catalogue(key: str, b: CatalogueIn, u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute("UPDATE catalogues SET name=%s, pages_label=%s WHERE key=%s RETURNING key",
                      (b.name.strip(), b.pages_label.strip(), key)).fetchone()
        if not r:
            raise HTTPException(404, "Catalogue not found")
    invalidate()
    return {"ok": True}


class FinishIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")


@admin.get("/finishes")
def list_finishes(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT name, color FROM finishes ORDER BY position, name").fetchall()


@admin.put("/finishes")
def save_finishes(b: List[FinishIn], u=Depends(current_user)):
    names = [f.name.strip() for f in b]
    if len(set(names)) != len(names) or not names:
        raise HTTPException(400, "Finish names must be unique and the list can't be empty")
    with db.conn() as c:
        c.execute("DELETE FROM finishes")
        for i, f in enumerate(b):
            c.execute("INSERT INTO finishes(name,color,position) VALUES(%s,%s,%s)", (f.name.strip(), f.color, i))
        c.execute("UPDATE products SET finishes = ARRAY(SELECT x FROM unnest(finishes) x WHERE x = ANY(%s))", (names,))
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- products

class ProductIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=140)
    collection_id: str
    catalogue_key: str
    code: str = Field("", max_length=20)
    pages: str = Field("", max_length=40)
    material: str = Field("", max_length=60)
    finishes: List[str] = []
    description: str = Field("", max_length=1500)
    image: str = ""
    gallery: List[str] = []
    is_new: bool = False
    active: bool = True
    subs: List[List[str]] = []
    seo_title: str = Field("", max_length=90)
    seo_desc: str = Field("", max_length=200)


@admin.get("/products")
def list_products(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute(
            "SELECT p.*, c.name AS collection_name, "
            "(SELECT count(*) FROM components x WHERE x.product_id=p.id) AS component_count "
            "FROM products p JOIN collections c ON c.id=p.collection_id "
            "ORDER BY p.position, p.id").fetchall()


def _product_values(c, b: ProductIn):
    if not c.execute("SELECT 1 FROM collections WHERE id=%s", (b.collection_id,)).fetchone():
        raise HTTPException(400, "Choose a category")
    if not c.execute("SELECT 1 FROM catalogues WHERE key=%s", (b.catalogue_key,)).fetchone():
        raise HTTPException(400, "Choose a catalogue")
    known = {r["name"] for r in c.execute("SELECT name FROM finishes").fetchall()}
    subs = [[s[0].strip(), (s[1] if len(s) > 1 else "").strip()] for s in b.subs if s and s[0].strip()]
    return (b.name.strip(), b.collection_id, b.catalogue_key, b.pages.strip(), b.is_new,
            Jsonb(subs) if subs else None, b.material.strip(), [f for f in b.finishes if f in known],
            asset_path(b.image), [asset_path(g) for g in b.gallery if g], b.description.strip(), b.active,
            b.seo_title.strip(), b.seo_desc.strip())


@admin.post("/products")
def create_product(b: ProductIn, u=Depends(current_user)):
    with db.conn() as c:
        v = _product_values(c, b)
        key = b.catalogue_key
        rows = c.execute("SELECT id FROM products WHERE id ~ %s", ("^%s-[0-9]+$" % re.escape(key),)).fetchall()
        n = max([int(r["id"].rsplit("-", 1)[1]) for r in rows] + [0]) + 1
        pid = "%s-%02d" % (key, n)
        code = b.code.strip() or "%s·%02d" % (key.upper(), n)
        pos = c.execute("SELECT coalesce(max(position),-1)+1 AS p FROM products").fetchone()["p"]
        c.execute(
            "INSERT INTO products(id,code,name,collection_id,catalogue_key,pages,is_new,subs,material,finishes,"
            "image,gallery,description,active,seo_title,seo_desc,position) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (pid, code) + v + (pos,))
    invalidate()
    return {"id": pid}


@admin.put("/products/{pid}")
def update_product(pid: str, b: ProductIn, u=Depends(current_user)):
    with db.conn() as c:
        v = _product_values(c, b)
        r = c.execute(
            "UPDATE products SET code=%s,name=%s,collection_id=%s,catalogue_key=%s,pages=%s,is_new=%s,subs=%s,"
            "material=%s,finishes=%s,image=%s,gallery=%s,description=%s,active=%s,seo_title=%s,seo_desc=%s,updated_at=now() "
            "WHERE id=%s RETURNING id",
            (b.code.strip() or pid.upper().replace("-", "·"),) + v + (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Product not found")
    invalidate()
    return {"ok": True}


@admin.delete("/products/{pid}")
def delete_product(pid: str, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM products WHERE id=%s", (pid,))
    invalidate()
    return {"ok": True}


class MoveIn(BaseModel):
    dir: int  # -1 up, +1 down


@admin.post("/products/{pid}/move")
def move_product(pid: str, b: MoveIn, u=Depends(current_user)):
    """Swap with the neighbouring series in the same catalogue (the order shown on the website)."""
    with db.conn() as c:
        # normalise positions first so every product has a unique slot
        for i, r in enumerate(c.execute("SELECT id FROM products ORDER BY position, id").fetchall()):
            c.execute("UPDATE products SET position=%s WHERE id=%s", (i, r["id"]))
        me_ = c.execute("SELECT id, catalogue_key, position FROM products WHERE id=%s", (pid,)).fetchone()
        if not me_:
            raise HTTPException(404, "Product not found")
        if b.dir < 0:
            o = c.execute("SELECT id, position FROM products WHERE catalogue_key=%s AND position < %s "
                          "ORDER BY position DESC LIMIT 1", (me_["catalogue_key"], me_["position"])).fetchone()
        else:
            o = c.execute("SELECT id, position FROM products WHERE catalogue_key=%s AND position > %s "
                          "ORDER BY position LIMIT 1", (me_["catalogue_key"], me_["position"])).fetchone()
        if o:
            c.execute("UPDATE products SET position=%s WHERE id=%s", (o["position"], pid))
            c.execute("UPDATE products SET position=%s WHERE id=%s", (me_["position"], o["id"]))
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- components (what's included in a series)

class ComponentIn(BaseModel):
    section: str = Field("", max_length=120)
    code: str = Field("", max_length=40)
    name: str = Field("", max_length=160)
    material: str = Field("", max_length=80)
    image: str = ""
    num: Optional[int] = None
    active: bool = True


@admin.get("/products/{pid}/components")
def list_components(pid: str, u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT * FROM components WHERE product_id=%s ORDER BY position, id", (pid,)).fetchall()


@admin.post("/products/{pid}/components")
def create_component(pid: str, b: ComponentIn, u=Depends(current_user)):
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM products WHERE id=%s", (pid,)).fetchone():
            raise HTTPException(404, "Product not found")
        pos = c.execute("SELECT coalesce(max(position),-1)+1 AS p FROM components WHERE product_id=%s", (pid,)).fetchone()["p"]
        r = c.execute("INSERT INTO components(product_id,section,num,code,name,material,image,position,active) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                      (pid, b.section.strip(), b.num, b.code.strip(), b.name.strip(), b.material.strip(),
                       asset_path(b.image), pos, b.active)).fetchone()
    invalidate()
    return {"id": r["id"]}


@admin.put("/components/{cid}")
def update_component(cid: int, b: ComponentIn, u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute("UPDATE components SET section=%s,num=%s,code=%s,name=%s,material=%s,image=%s,active=%s "
                      "WHERE id=%s RETURNING id",
                      (b.section.strip(), b.num, b.code.strip(), b.name.strip(), b.material.strip(),
                       asset_path(b.image), b.active, cid)).fetchone()
        if not r:
            raise HTTPException(404, "Component not found")
    invalidate()
    return {"ok": True}


@admin.delete("/components/{cid}")
def delete_component(cid: int, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM components WHERE id=%s", (cid,))
    invalidate()
    return {"ok": True}


@admin.post("/products/{pid}/components/reorder")
def reorder_components(pid: str, b: IntIdsIn, u=Depends(current_user)):
    with db.conn() as c:
        for i, cid in enumerate(b.ids):
            c.execute("UPDATE components SET position=%s WHERE id=%s AND product_id=%s", (i, cid, pid))
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- home page: featured, slides

@admin.get("/featured")
def get_featured(u=Depends(current_user)):
    with db.conn() as c:
        return [r["id"] for r in c.execute(
            "SELECT id FROM products WHERE featured ORDER BY featured_pos, position").fetchall()]


@admin.put("/featured")
def set_featured(b: IdsIn, u=Depends(current_user)):
    if len(b.ids) > 8:
        raise HTTPException(400, "Pick at most 8 featured products")
    with db.conn() as c:
        c.execute("UPDATE products SET featured=FALSE, featured_pos=0")
        for i, pid in enumerate(b.ids):
            c.execute("UPDATE products SET featured=TRUE, featured_pos=%s WHERE id=%s", (i, pid))
    invalidate()
    return {"ok": True}


class SlideIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=90)
    image: str
    collection_id: Optional[str] = None
    active: bool = True


@admin.get("/slides")
def list_slides(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT * FROM slides ORDER BY position, id").fetchall()


def _check_slides(c):
    if not c.execute("SELECT 1 FROM slides WHERE active").fetchone():
        raise HTTPException(400, "Keep at least one slide visible on the home page")


@admin.post("/slides")
def create_slide(b: SlideIn, u=Depends(current_user)):
    with db.conn() as c:
        pos = c.execute("SELECT coalesce(max(position),-1)+1 AS p FROM slides").fetchone()["p"]
        r = c.execute("INSERT INTO slides(title,image,collection_id,active,position) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                      (b.title.strip(), asset_path(b.image), b.collection_id or None, b.active, pos)).fetchone()
        _check_slides(c)
    invalidate()
    return {"id": r["id"]}


@admin.put("/slides/{sid}")
def update_slide(sid: int, b: SlideIn, u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute("UPDATE slides SET title=%s,image=%s,collection_id=%s,active=%s WHERE id=%s RETURNING id",
                      (b.title.strip(), asset_path(b.image), b.collection_id or None, b.active, sid)).fetchone()
        if not r:
            raise HTTPException(404, "Slide not found")
        _check_slides(c)
    invalidate()
    return {"ok": True}


@admin.delete("/slides/{sid}")
def delete_slide(sid: int, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM slides WHERE id=%s", (sid,))
        _check_slides(c)
    invalidate()
    return {"ok": True}


@admin.post("/slides/reorder")
def reorder_slides(b: IntIdsIn, u=Depends(current_user)):
    with db.conn() as c:
        reorder(c, "slides", b.ids)
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- contact details

class Center(BaseModel):
    city: str = Field(..., max_length=60)
    addr: str = Field("", max_length=300)
    phone: str = Field("", max_length=40)
    map: str = Field("", max_length=600)  # Google Maps link (optional)


class Office(BaseModel):
    tag: str = Field(..., max_length=80)
    addr: str = Field("", max_length=300)
    phones: List[str] = []
    email: str = Field("", max_length=160)
    map: str = Field("", max_length=600)


@admin.get("/contact-info")
def get_contact(u=Depends(current_user)):
    with db.conn() as c:
        return {"centers": db.get_setting(c, "centers", []), "offices": db.get_setting(c, "offices", [])}


class ContactIn(BaseModel):
    centers: List[Center]
    offices: List[Office]


@admin.put("/contact-info")
def save_contact(b: ContactIn, u=Depends(current_user)):
    with db.conn() as c:
        centers, offices = [x.model_dump() for x in b.centers], [x.model_dump() for x in b.offices]
        for x in centers + offices:
            x["map"] = clean_url(x["map"], "Google Maps link")
        db.set_setting(c, "centers", centers)
        db.set_setting(c, "offices", offices)
    invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- enquiries

@admin.get("/enquiries")
def list_enquiries(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT * FROM enquiries ORDER BY created_at DESC LIMIT 1000").fetchall()


class StatusIn(BaseModel):
    status: str = Field(..., pattern="^(new|done)$")


@admin.put("/enquiries/{eid}")
def set_enquiry(eid: int, b: StatusIn, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("UPDATE enquiries SET status=%s WHERE id=%s", (b.status, eid))
    return {"ok": True}


@admin.delete("/enquiries/{eid}")
def delete_enquiry(eid: int, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM enquiries WHERE id=%s", (eid,))
    return {"ok": True}


@admin.get("/enquiries.csv")
def export_enquiries(u=Depends(current_user)):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Received", "Topic", "Name", "Phone", "Email", "City", "Message", "Items in list", "Status"])
    for r in rows:
        w.writerow([r["created_at"].strftime("%Y-%m-%d %H:%M"), r["topic"], r["name"], r["phone"], r["email"],
                    r["city"], r["message"], r["items_count"], r["status"]])
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="sap-enquiries.csv"'})


# --------------------------------------------------------------------------- uploads

@admin.post("/upload")
async def upload(file: UploadFile = File(...), u=Depends(current_user)):
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Image is larger than 15 MB")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise HTTPException(400, "That file isn't a usable image (use JPG, PNG or WebP)")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "PA") else "RGB")
    im.thumbnail((2000, 2000), Image.LANCZOS)
    name = uuid.uuid4().hex[:16] + ".webp"
    im.save(UPLOAD_DIR / name, "WEBP", quality=84, method=4)
    return {"path": "uploads/" + name, "width": im.width, "height": im.height}


# --------------------------------------------------------------------------- site settings (SEO, founder, legal, email)

class SiteIn(BaseModel):
    description: str = Field("", max_length=400)
    share_image: str = ""
    ga4: str = Field("", max_length=20)
    gsc_verification: str = Field("", max_length=120)
    bing_verification: str = Field("", max_length=120)
    site_url: str = Field("", max_length=200)


@admin.get("/settings/site")
def get_site(u=Depends(current_user)):
    with db.conn() as c:
        return get_json(c, "site", defaults.SITE)


@admin.put("/settings/site")
def save_site(b: SiteIn, u=Depends(current_user)):
    ga = b.ga4.strip().upper()
    if ga and not re.fullmatch(r"G-[A-Z0-9]{4,14}", ga):
        raise HTTPException(400, "The Google Analytics ID looks like G-XXXXXXXXXX")
    tok = re.compile(r"^[\w\-]{0,120}$")
    for v in (b.gsc_verification.strip(), b.bing_verification.strip()):
        if not tok.match(v):
            raise HTTPException(400, "Paste only the verification code, not the whole tag")
    with db.conn() as c:
        db.set_setting(c, "site", {"description": b.description.strip() or defaults.SITE["description"],
                                   "share_image": asset_path(b.share_image), "ga4": ga,
                                   "gsc_verification": b.gsc_verification.strip(), "bing_verification": b.bing_verification.strip(),
                                   "site_url": clean_url(b.site_url, "website address").rstrip("/")})
    invalidate()
    return {"ok": True}


class Milestone(BaseModel):
    year: str = Field("", max_length=12)
    label: str = Field("", max_length=140)


class Value(BaseModel):
    title: str = Field("", max_length=40)
    text: str = Field("", max_length=200)


class FounderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    role: str = Field("", max_length=80)
    photo: str = ""
    headline: str = Field("", max_length=120)
    intro: str = Field("", max_length=600)
    story: List[str] = []
    vision: str = Field("", max_length=600)
    values: List[Value] = []
    milestones: List[Milestone] = []


@admin.get("/settings/founder")
def get_founder(u=Depends(current_user)):
    with db.conn() as c:
        return get_json(c, "founder", defaults.FOUNDER)


@admin.put("/settings/founder")
def save_founder(b: FounderIn, u=Depends(current_user)):
    d = b.model_dump()
    d["photo"] = asset_path(b.photo)
    d["story"] = [t.strip() for t in b.story if t.strip()][:12]
    d["values"] = [v for v in d["values"] if v["title"].strip()][:8]
    d["milestones"] = [m for m in d["milestones"] if m["label"].strip()][:10]
    with db.conn() as c:
        db.set_setting(c, "founder", d)
    invalidate()
    return {"ok": True}


class LegalDoc(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    updated: str = Field("", max_length=40)
    body: str = Field("", max_length=30000)


class LegalIn(BaseModel):
    privacy: LegalDoc
    cookies: LegalDoc
    terms: LegalDoc


@admin.get("/settings/legal")
def get_legal(u=Depends(current_user)):
    with db.conn() as c:
        return {k: {**defaults.LEGAL[k], **((db.get_setting(c, "legal", {}) or {}).get(k, {}))} for k in defaults.LEGAL}


@admin.put("/settings/legal")
def save_legal(b: LegalIn, u=Depends(current_user)):
    with db.conn() as c:
        db.set_setting(c, "legal", b.model_dump())
    invalidate()
    return {"ok": True}


class EmailIn(BaseModel):
    to: List[str] = []
    host: str = Field("", max_length=160)
    port: int = Field(587, ge=1, le=65535)
    user: str = Field("", max_length=160)
    password: str = Field("", max_length=200)  # blank = keep the saved one
    from_addr: str = Field("", max_length=160)
    from_name: str = Field("", max_length=80)


def _email_public(c):
    cfg = get_json(c, "email", defaults.EMAIL)
    env = bool(os.environ.get("SMTP_HOST"))
    return {"to": cfg.get("to", []), "host": cfg.get("host", ""), "port": cfg.get("port", 587), "user": cfg.get("user", ""),
            "from_addr": cfg.get("from_addr", ""), "from_name": cfg.get("from_name", ""),
            "has_password": bool(cfg.get("password_enc")), "from_env": env}


@admin.get("/settings/email")
def get_email(u=Depends(current_user)):
    with db.conn() as c:
        return _email_public(c)


@admin.put("/settings/email")
def save_email(b: EmailIn, u=Depends(current_user)):
    to = [t.strip() for t in b.to if t.strip()]
    for t in to:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
            raise HTTPException(400, "“%s” is not a valid email address" % t)
    with db.conn() as c:
        old = get_json(c, "email", defaults.EMAIL)
        enc = mailer.encrypt(_secret, b.password) if b.password else old.get("password_enc", "")
        db.set_setting(c, "email", {"to": to, "host": b.host.strip(), "port": b.port, "user": b.user.strip(),
                                    "from_addr": b.from_addr.strip(), "from_name": b.from_name.strip() or "SAP Hardware website",
                                    "password_enc": enc})
    return {"ok": True}


@admin.post("/settings/email/test")
def test_email(u=Depends(current_user)):
    with db.conn() as c:
        conf = mailer.effective(get_json(c, "email", defaults.EMAIL), _secret)
    try:
        mailer.send(conf, "SAP Hardware website: test email",
                    "This is a test message from the SAP Hardware website admin.\n\nIf you can read this, enquiry emails will arrive here.")
    except Exception as e:
        raise HTTPException(400, "Could not send: %s" % str(e)[:300])
    return {"ok": True, "sent_to": conf["to"]}


# --------------------------------------------------------------------------- downloads (PDF links with cover images)

class DocumentIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=200)
    url: str = Field(..., min_length=8, max_length=800)
    cover: str = ""
    catalogue_key: str = Field("", max_length=10)
    active: bool = True


@admin.get("/documents")
def list_documents(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute("SELECT * FROM documents ORDER BY position, id").fetchall()


@admin.post("/documents")
def create_document(b: DocumentIn, u=Depends(current_user)):
    with db.conn() as c:
        pos = c.execute("SELECT coalesce(max(position),-1)+1 AS p FROM documents").fetchone()["p"]
        r = c.execute("INSERT INTO documents(title,note,url,cover,catalogue_key,position,active) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                      (b.title.strip(), b.note.strip(), clean_url(b.url, "PDF link"), asset_path(b.cover), b.catalogue_key, pos, b.active)).fetchone()
    invalidate()
    return {"id": r["id"]}


@admin.put("/documents/{did}")
def update_document(did: int, b: DocumentIn, u=Depends(current_user)):
    with db.conn() as c:
        r = c.execute("UPDATE documents SET title=%s,note=%s,url=%s,cover=%s,catalogue_key=%s,active=%s WHERE id=%s RETURNING id",
                      (b.title.strip(), b.note.strip(), clean_url(b.url, "PDF link"), asset_path(b.cover), b.catalogue_key, b.active, did)).fetchone()
        if not r:
            raise HTTPException(404, "Download not found")
    invalidate()
    return {"ok": True}


@admin.delete("/documents/{did}")
def delete_document(did: int, u=Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM documents WHERE id=%s", (did,))
    invalidate()
    return {"ok": True}


@admin.post("/documents/reorder")
def reorder_documents(b: IntIdsIn, u=Depends(current_user)):
    with db.conn() as c:
        reorder(c, "documents", b.ids)
    invalidate()
    return {"ok": True}


app.include_router(admin)

# --------------------------------------------------------------------------- admin UI + site

SEC_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
               "X-Frame-Options": "SAMEORIGIN"}


def _safe(base: Path, rel: str) -> Optional[Path]:
    p = (base / rel).resolve()
    return p if p.is_file() and (base == p.parent or base in p.parents) else None


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_index():
    return FileResponse(ADMIN_DIR / "index.html", headers={"Cache-Control": "no-cache", **SEC_HEADERS,
                                                          "X-Robots-Tag": "noindex"})


@app.get("/admin/{name}", include_in_schema=False)
def admin_static(name: str):
    p = _safe(ADMIN_DIR, name)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex"})


@app.get("/healthz", include_in_schema=False)
def healthz():
    with db.conn() as c:
        c.execute("SELECT 1")
    return {"ok": True}


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request):
    base = base_url(request, build_public_data()["site"])
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\n\nSitemap: %s/sitemap.xml\n" % base)


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    d = build_public_data()
    base = base_url(request, d["site"])
    urls = [("/", "1.0"), ("/products.html", "0.9"), ("/catalogues.html", "0.8"), ("/about.html", "0.6"), ("/contact.html", "0.6"),
            ("/privacy-policy", "0.2"), ("/cookie-policy", "0.2"), ("/terms", "0.2")]
    urls += [("/products.html?c=" + c["id"], "0.7") for c in d["collections"]]
    urls += [("/product.html?id=" + p["id"], "0.8") for p in d["products"]]
    imgs = {p["id"]: p["img"] for p in d["products"]}
    esc = seo.esc
    body = ""
    for u, pr in urls:
        im = ""
        if u.startswith("/product.html?id="):
            src = imgs.get(u.split("=", 1)[1])
            if src:
                im = "<image:image><image:loc>%s/%s</image:loc></image:image>" % (base, esc(src.lstrip("/")))
        body += "<url><loc>%s%s</loc><priority>%s</priority>%s</url>" % (base, esc(u), pr, im)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                    'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">' + body + "</urlset>", media_type="application/xml")


def _render(p: Path, request: Request, status: int = 200, path: Optional[str] = None):
    """Serve an HTML page with live data injected and its SEO tags/structured data/crawler content filled in."""
    text = p.read_text(encoding="utf-8")
    data = dict(build_public_data())
    base = base_url(request, data["site"])
    path = path or request.url.path
    q = dict(request.query_params)
    route = seo.norm_path(path)
    comps = row = None
    page = None
    if route == "/product" and q.get("id"):
        with db.conn() as c:
            row = c.execute("SELECT seo_title, seo_desc FROM products WHERE id=%s", (q["id"],)).fetchone()
            comps = c.execute("SELECT name, code FROM components WHERE product_id=%s AND active ORDER BY position, id", (q["id"],)).fetchall()
    if route in seo.LEGAL_ROUTES:
        key = seo.LEGAL_ROUTES[route]
        with db.conn() as c:
            custom = (db.get_setting(c, "legal", {}) or {})
        data["legal"] = {k: {**defaults.LEGAL[k], **custom.get(k, {})} for k in defaults.LEGAL}
        page = {"key": key, **data["legal"][key]}
    m = seo.page_meta(path, q, data, base, comps, row)
    if status == 200 and route == "/product" and m["robots"].startswith("noindex"):
        status = 404
    text = _inject(text, page)
    text = seo.apply(text, m, data["site"], seo.nav_links(base))
    return HTMLResponse(text, status_code=status, headers={"Cache-Control": "no-cache", **SEC_HEADERS})


_og_cache = {}


def _og(kind: str, key: str):
    d = build_public_data()
    if kind == "p":
        pr = next((x for x in d["products"] if x["id"] == key), None)
        if not pr:
            raise HTTPException(404)
        col = next((c for c in d["collections"] if c["id"] == pr["col"]), {})
        args = (pr["name"], col.get("name", "Catalogue"), "%s · %d components" % (pr["code"], pr["n"]) if pr["n"] else pr["code"], pr["img"])
    elif kind == "c":
        col = next((c for c in d["collections"] if c["id"] == key), None)
        if not col:
            raise HTTPException(404)
        first = next((x for x in d["products"] if x["col"] == key), None)
        args = (col["name"], "Collection", "%d series" % len([x for x in d["products"] if x["col"] == key]), first["img"] if first else col["scene"])
    else:
        hero = d["slides"][0]["img"] if d["slides"] else ""
        args = (seo.NAME, seo.TAGLINE, "%d series · 3,000+ products" % len(d["products"]), hero)
    if args not in _og_cache:
        if len(_og_cache) > 200:
            _og_cache.clear()
        _og_cache[args] = seo.share_image(SITE_DIR, *args)
    return Response(_og_cache[args], media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/og/home.jpg", include_in_schema=False)
def og_home():
    return _og("h", "")


@app.get("/og/{kind}/{key}.jpg", include_in_schema=False)
def og_item(kind: str, key: str):
    if kind not in ("p", "c"):
        raise HTTPException(404)
    return _og(kind, key)


@app.get("/uploads/{name}", include_in_schema=False)
def uploaded(name: str):
    p = _safe(UPLOAD_DIR, name)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/{path:path}", include_in_schema=False)
def site(path: str, request: Request):
    if path.startswith("api/"):
        raise HTTPException(404)
    rel = path.strip("/") or "index.html"
    if path.strip("/") == "index.html":  # the home page lives at "/"; send the duplicate URL there
        return RedirectResponse("/", status_code=301)
    if seo.norm_path(path) in seo.LEGAL_ROUTES:
        return _render(SITE_DIR / "legal.html", request)
    p = _safe(SITE_DIR, rel)
    if not p and "." not in rel:
        p = _safe(SITE_DIR, rel + ".html")  # clean URLs: /about -> about.html
    if not p:
        nf = SITE_DIR / "404.html"
        return _render(nf, request, 404, "/__not_found__") if nf.exists() else PlainTextResponse("Not found", status_code=404)
    if p.suffix == ".html":
        return _render(p, request)
    ttl = "public, max-age=31536000" if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".svg") else "no-cache"
    return FileResponse(p, headers={"Cache-Control": ttl, **SEC_HEADERS})
