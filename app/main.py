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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from PIL import Image, ImageOps
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, db

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

# --------------------------------------------------------------------------- public data

_cache = {"at": 0.0, "data": None}


def invalidate():
    _cache["at"] = 0.0


def build_public_data():
    if _cache["data"] is not None and time.time() - _cache["at"] < 30:
        return _cache["data"]
    with db.conn() as c:
        cols = c.execute("SELECT * FROM collections WHERE active ORDER BY position, name").fetchall()
        cats = c.execute("SELECT * FROM catalogues ORDER BY position").fetchall()
        fins = c.execute("SELECT * FROM finishes ORDER BY position, name").fetchall()
        prods = c.execute(
            "SELECT p.* FROM products p JOIN collections c ON c.id=p.collection_id "
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
                      "desc": r["description"]} for r in prods],
        "slides": [{"title": r["title"], "img": r["image"], "col": r["collection_id"] if r["col_name"] else "",
                    "label": r["col_name"] or "SAP Hardware"} for r in slides],
        "featured": [r["id"] for r in feat],
        "centers": centers,
        "offices": offices,
    }
    _cache.update(at=time.time(), data=data)
    return data


def _inject(html: str) -> str:
    payload = json.dumps(build_public_data(), ensure_ascii=False).replace("</", "<\\/").replace(" ", "\\u2028")
    tag = "<script>window.__SAP_DATA=%s;</script>" % payload
    return re.sub(r"<head>", lambda m: "<head>" + tag, html, count=1, flags=re.I)


@app.get("/api/data")
def public_data():
    return JSONResponse(build_public_data(), headers={"Cache-Control": "no-cache"})


class EnquiryIn(BaseModel):
    topic: str = Field("product", max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=1, max_length=40)
    email: str = Field("", max_length=160)
    city: str = Field("", max_length=120)
    message: str = Field("", max_length=4000)
    items: int = Field(0, ge=0, le=1000)


@app.post("/api/enquiries")
def create_enquiry(e: EnquiryIn, request: Request):
    ip = request.client.host if request.client else ""
    if not enquiry_throttle.hit(ip):
        raise HTTPException(429, "Too many requests. Please try again in a few minutes.")
    topic = e.topic if e.topic in ("product", "dist", "visit") else "product"
    with db.conn() as c:
        c.execute("INSERT INTO enquiries(topic,name,phone,email,city,message,items_count,ip) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                  (topic, e.name.strip(), e.phone.strip(), e.email.strip(), e.city.strip(), e.message.strip(), e.items, ip))
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


@admin.get("/products")
def list_products(u=Depends(current_user)):
    with db.conn() as c:
        return c.execute(
            "SELECT p.*, c.name AS collection_name FROM products p JOIN collections c ON c.id=p.collection_id "
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
            asset_path(b.image), [asset_path(g) for g in b.gallery if g], b.description.strip(), b.active)


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
            "image,gallery,description,active,position) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (pid, code) + v + (pos,))
    invalidate()
    return {"id": pid}


@admin.put("/products/{pid}")
def update_product(pid: str, b: ProductIn, u=Depends(current_user)):
    with db.conn() as c:
        v = _product_values(c, b)
        r = c.execute(
            "UPDATE products SET code=%s,name=%s,collection_id=%s,catalogue_key=%s,pages=%s,is_new=%s,subs=%s,"
            "material=%s,finishes=%s,image=%s,gallery=%s,description=%s,active=%s,updated_at=now() "
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
    """Swap with the neighbouring product in the same category."""
    with db.conn() as c:
        me_ = c.execute("SELECT id, collection_id, position FROM products WHERE id=%s", (pid,)).fetchone()
        if not me_:
            raise HTTPException(404, "Product not found")
        if b.dir < 0:
            o = c.execute("SELECT id, position FROM products WHERE collection_id=%s AND (position, id) < (%s, %s) "
                          "ORDER BY position DESC, id DESC LIMIT 1", (me_["collection_id"], me_["position"], pid)).fetchone()
        else:
            o = c.execute("SELECT id, position FROM products WHERE collection_id=%s AND (position, id) > (%s, %s) "
                          "ORDER BY position, id LIMIT 1", (me_["collection_id"], me_["position"], pid)).fetchone()
        if o:
            if o["position"] == me_["position"]:  # tie: renumber everything stably first
                for i, r in enumerate(c.execute("SELECT id FROM products ORDER BY position, id").fetchall()):
                    c.execute("UPDATE products SET position=%s WHERE id=%s", (i, r["id"]))
                me_ = c.execute("SELECT position FROM products WHERE id=%s", (pid,)).fetchone()
                o = c.execute("SELECT position FROM products WHERE id=%s", (o["id"],)).fetchone() | {"id": o["id"]}
            c.execute("UPDATE products SET position=%s WHERE id=%s", (o["position"], pid))
            c.execute("UPDATE products SET position=%s WHERE id=%s", (me_["position"], o["id"]))
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


class IntIdsIn(BaseModel):
    ids: List[int]


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


class Office(BaseModel):
    tag: str = Field(..., max_length=80)
    addr: str = Field("", max_length=300)
    phones: List[str] = []
    email: str = Field("", max_length=160)


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
        db.set_setting(c, "centers", [x.model_dump() for x in b.centers])
        db.set_setting(c, "offices", [x.model_dump() for x in b.offices])
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
    base = str(request.base_url).rstrip("/")
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /admin\n\nSitemap: %s/sitemap.xml\n" % base)


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    d = build_public_data()
    urls = [("/", "1.0"), ("/products.html", "0.8"), ("/about.html", "0.6"), ("/contact.html", "0.6")]
    urls += [("/products.html?c=" + c["id"], "0.7") for c in d["collections"]]
    urls += [("/product.html?id=" + p["id"], "0.6") for p in d["products"]]
    body = "".join("<url><loc>%s%s</loc><priority>%s</priority></url>" % (base, u.replace("&", "&amp;"), pr)
                   for u, pr in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    + body + "</urlset>", media_type="application/xml")


def _html(p: Path, status: int = 200):
    return HTMLResponse(_inject(p.read_text(encoding="utf-8")), status_code=status,
                        headers={"Cache-Control": "no-cache", **SEC_HEADERS})


@app.get("/uploads/{name}", include_in_schema=False)
def uploaded(name: str):
    p = _safe(UPLOAD_DIR, name)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/{path:path}", include_in_schema=False)
def site(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    rel = path.strip("/") or "index.html"
    p = _safe(SITE_DIR, rel)
    if not p and "." not in rel:
        p = _safe(SITE_DIR, rel + ".html")  # clean URLs: /about -> about.html
    if not p:
        nf = SITE_DIR / "404.html"
        return _html(nf, 404) if nf.exists() else PlainTextResponse("Not found", status_code=404)
    if p.suffix == ".html":
        return _html(p)
    ttl = "public, max-age=31536000" if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".svg") else "public, max-age=3600"
    return FileResponse(p, headers={"Cache-Control": ttl, **SEC_HEADERS})
