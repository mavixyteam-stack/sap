"""On-page SEO: titles, descriptions, canonical URLs, Open Graph / Twitter tags, JSON-LD, crawler fallback
content and generated share images. Everything is produced on the server so crawlers and social
scrapers (which do not run JavaScript) see it."""
import html
import io
import json
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

NAME = "SAP Hardware"
TAGLINE = "Architectural & Furniture Fittings"
LEGAL_ROUTES = {"/privacy-policy": "privacy", "/cookie-policy": "cookies", "/terms": "terms"}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0].rstrip(",.;:- ")
    return cut + "…"


def norm_path(path: str) -> str:
    p = "/" + path.strip("/")
    p = re.sub(r"\.html$", "", p)
    return "/" if p in ("/", "/index") else p


def _find(lst, key, val):
    return next((x for x in lst if x.get(key) == val), None)


def page_meta(path: str, query: dict, data: dict, base: str, comps: Optional[list] = None, row: Optional[dict] = None) -> dict:
    """Return everything needed to describe one page to search engines and social networks."""
    p = norm_path(path)
    site = data.get("site", {})
    default_desc = site.get("description") or ""
    m = dict(title="", desc="", canonical=base + "/", robots="index,follow,max-image-preview:large,max-snippet:-1",
             og_type="website", image=base + "/og/home.jpg", alt=NAME + " — " + TAGLINE, jsonld=[], body="", crumbs=[])
    if site.get("share_image"):
        m["image"] = base + "/" + site["share_image"].lstrip("/")
    org = {"@type": "Organization", "@id": base + "/#org", "name": NAME, "legalName": "Jagannath Hardware Pvt. Ltd.",
           "url": base + "/", "logo": base + "/icon-512.png", "foundingDate": "2013",
           "slogan": "A Quality Product — " + TAGLINE, "description": default_desc,
           "founder": {"@type": "Person", "name": (data.get("founder") or {}).get("name", "Jitendra Agarwal")}}
    off = (data.get("offices") or [{}])[0]
    if off:
        org["address"] = {"@type": "PostalAddress", "streetAddress": off.get("addr", ""), "addressCountry": "IN"}
        if off.get("phones"):
            org["telephone"] = off["phones"][0]
        if off.get("email"):
            org["email"] = off["email"]

    prods, cols = data.get("products", []), data.get("collections", [])
    if p == "/":
        m["title"] = "SAP Hardware | Architectural & Furniture Fittings"
        m["desc"] = clip(default_desc, 158)
        m["jsonld"] = [org, {"@type": "WebSite", "@id": base + "/#site", "url": base + "/", "name": NAME, "publisher": {"@id": base + "/#org"},
                             "potentialAction": {"@type": "SearchAction", "target": base + "/products.html?q={search_term_string}",
                                                 "query-input": "required name=search_term_string"}}]
        links = "".join('<li><a href="%s/products.html?c=%s">%s</a>: %s</li>' % (base, esc(c["id"]), esc(c["name"]), esc(c["blurb"])) for c in cols)
        feat = "".join('<li><a href="%s/product.html?id=%s">%s</a></li>' % (base, esc(x["id"]), esc(x["name"])) for x in prods[:40])
        m["body"] = "<h1>%s — %s</h1><p>%s</p><h2>Collections</h2><ul>%s</ul><h2>Series</h2><ul>%s</ul>" % (NAME, TAGLINE, esc(default_desc), links, feat)
    elif p == "/products":
        cid = query.get("c", "")
        col = _find(cols, "id", cid) if cid else None
        cat = query.get("cat", "")
        if col:
            m["title"] = "%s — %s | SAP Hardware" % (col["name"], "Series & Components")
            m["desc"] = clip("%s %d series in this collection, each a complete system with every component listed." % (col["blurb"], len([x for x in prods if x["col"] == cid])), 158)
            m["canonical"] = "%s/products.html?c=%s" % (base, cid)
            m["image"] = "%s/og/c/%s.jpg" % (base, cid)
            m["alt"] = col["name"]
            m["crumbs"] = [("Products", base + "/products.html"), (col["name"], m["canonical"])]
            items = [x for x in prods if x["col"] == cid]
        else:
            m["title"] = "All Products — %d Series, Complete Systems | SAP Hardware" % len(prods)
            m["desc"] = clip("Browse every SAP Hardware series, grouped like the printed catalogue: aluminium profiles, glass systems, sliding and folding fittings, door hardware, kitchen and wardrobe solutions.", 158)
            m["canonical"] = base + "/products.html"
            m["crumbs"] = [("Products", m["canonical"])]
            items = prods
        if query.get("q") or query.get("new") or cat:
            m["robots"] = "noindex,follow"
        m["jsonld"] = [{"@type": "CollectionPage", "name": m["title"], "url": m["canonical"], "isPartOf": {"@id": base + "/#site"}},
                       {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": "%s/product.html?id=%s" % (base, x["id"]), "name": x["name"]} for i, x in enumerate(items[:100])]}]
        m["body"] = "<h1>%s</h1><p>%s</p><ul>%s</ul>" % (esc(col["name"] if col else "All products"), esc(m["desc"]),
                    "".join('<li><a href="%s/product.html?id=%s">%s</a> (%s) — %s</li>' % (base, esc(x["id"]), esc(x["name"]), esc(x["code"]), esc(x["desc"])) for x in items))
    elif p == "/product":
        pid = query.get("id", "")
        pr = _find(prods, "id", pid)
        if not pr:
            m.update(title="Product not found | SAP Hardware", robots="noindex,follow", canonical=base + "/products.html", desc=clip(default_desc, 158))
            return m
        col = _find(cols, "id", pr["col"]) or {}
        row = row or {}
        m["title"] = clip(row.get("seo_title") or "%s — %s | SAP Hardware" % (pr["name"], col.get("name", "Catalogue")), 70)
        base_desc = row.get("seo_desc") or pr.get("desc") or ""
        tail = " Catalogue pp. %s." % pr["pages"] if pr.get("pages") else ""
        m["desc"] = clip(("%s%s" % (base_desc, tail)) if base_desc else "%s (%s) from the SAP Hardware %s collection.%s" % (pr["name"], pr["code"], col.get("name", ""), tail), 158)
        m["canonical"] = "%s/product.html?id=%s" % (base, pid)
        m["og_type"] = "product"
        m["image"] = "%s/og/p/%s.jpg" % (base, pid)
        m["alt"] = "%s — SAP Hardware" % pr["name"]
        m["crumbs"] = [("Products", base + "/products.html"), (col.get("name", "Catalogue"), "%s/products.html?c=%s" % (base, pr["col"])), (pr["name"], m["canonical"])]
        imgs = [base + "/" + x.lstrip("/") for x in ([pr["img"]] + (pr.get("gallery") or [])) if x]
        node = {"@type": "Product", "@id": m["canonical"] + "#product", "name": pr["name"], "sku": pr["code"], "mpn": pr["code"],
                "url": m["canonical"], "description": m["desc"], "image": imgs, "category": col.get("name", ""),
                "brand": {"@type": "Brand", "name": NAME}, "manufacturer": {"@id": base + "/#org"}}
        if comps:
            node["hasPart"] = [{"@type": "Product", "name": c["name"], "sku": c["code"]} for c in comps[:60] if c.get("name")]
        m["jsonld"] = [node]
        sections = ""
        if comps:
            sections = "<h2>What’s included</h2><ul>%s</ul>" % "".join("<li>%s %s</li>" % (esc(c["name"]), esc(c["code"])) for c in comps)
        m["body"] = "<h1>%s</h1><p>%s</p><p>Series %s · Catalogue pages %s</p>%s" % (esc(pr["name"]), esc(m["desc"]), esc(pr["code"]), esc(pr["pages"]), sections)
    elif p == "/catalogues":
        docs = data.get("documents", [])
        m["title"] = "Catalogues \u2014 Download SAP Hardware PDF Catalogues"
        m["desc"] = clip("Browse the SAP Hardware range online, grouped like the printed catalogues, or view and download the catalogue PDFs: aluminium profiles, glass systems, sliding fittings, door hardware, kitchen and wardrobe solutions.", 158)
        m["canonical"] = base + "/catalogues.html"
        m["crumbs"] = [("Catalogues", m["canonical"])]
        m["jsonld"] = [{"@type": "CollectionPage", "name": m["title"], "url": m["canonical"], "isPartOf": {"@id": base + "/#site"}},
                       {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": d["title"], "url": d["view"]} for i, d in enumerate(docs)]}]
        m["body"] = "<h1>SAP Hardware catalogues</h1><p>%s</p><ul>%s</ul><h2>Browse online</h2><ul>%s</ul>" % (
            esc(m["desc"]), "".join('<li><a href="%s">%s</a> \u2014 %s</li>' % (esc(d["view"]), esc(d["title"]), esc(d["note"])) for d in docs),
            "".join('<li><a href="%s/products.html?cat=%s">%s</a> (%s series)</li>' % (base, esc(k["key"]), esc(k["name"]), k["count"]) for k in data.get("catalogues", [])))
    elif p == "/about":
        f = data.get("founder") or {}
        m["title"] = "About SAP Hardware — Founded in 2013 by %s" % f.get("name", "Jitendra Agarwal")
        m["desc"] = clip("%s %s" % (f.get("intro", ""), "From 7 products in 2013 to 3,000+ today, with display centres in Bengaluru, Chennai, Surat and Jodhpur."), 158)
        m["canonical"] = base + "/about.html"
        m["og_type"] = "article"
        m["crumbs"] = [("About", m["canonical"])]
        m["jsonld"] = [org, {"@type": "AboutPage", "url": m["canonical"], "name": m["title"]},
                       {"@type": "Person", "name": f.get("name", ""), "jobTitle": "Founder", "worksFor": {"@id": base + "/#org"},
                        "image": base + "/" + (f.get("photo") or "").lstrip("/")}]
        m["body"] = "<h1>About SAP Hardware</h1><p>%s</p><h2>%s</h2><p>%s</p>%s<p>%s</p>" % (
            esc(default_desc), esc(f.get("name", "")), esc(f.get("intro", "")), "".join("<p>%s</p>" % esc(t) for t in f.get("story", [])), esc(f.get("vision", "")))
        if f.get("photo"):
            m["image"] = base + "/" + f["photo"].lstrip("/")
            m["alt"] = f.get("name", "")
    elif p == "/contact":
        m["title"] = "Contact SAP Hardware — Enquiries, Distributorship & Display Centres"
        m["desc"] = clip("Send a product enquiry, ask about distributorship or visit a SAP Hardware display centre in Bengaluru, Chennai, Surat or Jodhpur.", 158)
        m["canonical"] = base + "/contact.html"
        m["crumbs"] = [("Contact", m["canonical"])]
        biz = []
        for c in data.get("centers", []):
            node = {"@type": "Store", "name": "SAP Hardware Display Centre — %s" % c.get("city", ""), "parentOrganization": {"@id": base + "/#org"},
                    "address": {"@type": "PostalAddress", "streetAddress": c.get("addr", ""), "addressLocality": c.get("city", ""), "addressCountry": "IN"},
                    "telephone": c.get("phone", ""), "image": base + "/icon-512.png"}
            if c.get("map"):
                node["hasMap"] = c["map"]
            biz.append(node)
        m["jsonld"] = [org, {"@type": "ContactPage", "url": m["canonical"], "name": m["title"]}] + biz
        m["body"] = "<h1>Contact SAP Hardware</h1><p>%s</p><ul>%s</ul>" % (esc(m["desc"]), "".join(
            "<li>%s: %s, %s</li>" % (esc(c.get("city")), esc(c.get("addr")), esc(c.get("phone"))) for c in data.get("centers", [])))
    elif p in LEGAL_ROUTES:
        doc = (data.get("legal") or {}).get(LEGAL_ROUTES[p], {})
        m["title"] = "%s | SAP Hardware" % doc.get("title", "Policy")
        m["desc"] = clip("%s for the SAP Hardware website. Last updated %s." % (doc.get("title", ""), doc.get("updated", "")), 158)
        m["canonical"] = base + p
        m["crumbs"] = [(doc.get("title", ""), m["canonical"])]
        m["body"] = "<h1>%s</h1>%s" % (esc(doc.get("title")), "".join("<p>%s</p>" % esc(x) for x in (doc.get("body", "").split("\n"))))
    else:
        m.update(title="Page not found | SAP Hardware", robots="noindex,follow", desc=clip(default_desc, 158), canonical=base + "/")
        return m
    if m["crumbs"]:
        home = [("Home", base + "/")]
        m["jsonld"].append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(home + m["crumbs"])]})
    return m


def head_html(m: dict, site: dict) -> str:
    t = esc(m["title"]); d = esc(m["desc"]); c = esc(m["canonical"]); img = esc(m["image"]); alt = esc(m["alt"])
    out = [
        "<title>%s</title>" % t,
        '<meta name="description" content="%s">' % d,
        '<link rel="canonical" href="%s">' % c,
        '<meta name="robots" content="%s">' % esc(m["robots"]),
        '<meta property="og:site_name" content="%s">' % NAME,
        '<meta property="og:locale" content="en_IN">',
        '<meta property="og:type" content="%s">' % esc(m["og_type"]),
        '<meta property="og:title" content="%s">' % t,
        '<meta property="og:description" content="%s">' % d,
        '<meta property="og:url" content="%s">' % c,
        '<meta property="og:image" content="%s">' % img,
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="%s">' % alt,
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="%s">' % t,
        '<meta name="twitter:description" content="%s">' % d,
        '<meta name="twitter:image" content="%s">' % img,
        '<meta name="twitter:image:alt" content="%s">' % alt,
    ]
    if site.get("gsc_verification"):
        out.append('<meta name="google-site-verification" content="%s">' % esc(site["gsc_verification"]))
    if site.get("bing_verification"):
        out.append('<meta name="msvalidate.01" content="%s">' % esc(site["bing_verification"]))
    if m["jsonld"]:
        blob = json.dumps({"@context": "https://schema.org", "@graph": m["jsonld"]}, ensure_ascii=False).replace("</", "<\\/")
        out.append('<script type="application/ld+json">%s</script>' % blob)
    return "\n".join(out)


HELMET_SEO = re.compile(
    r"<title>.*?</title>\s*|<meta\s+name=\"robots\"[^>]*>\s*|<meta\s+name=\"description\"[^>]*>\s*|<meta\s+property=\"og:[^>]*>\s*|<meta\s+name=\"twitter:[^>]*>\s*|<link\s+rel=\"canonical\"[^>]*>\s*",
    re.S | re.I)


def apply(html_text: str, m: dict, site: dict, nav: str = "") -> str:
    """Swap the page's static title/meta for the correct ones in the real <head>, add crawler content."""
    cleaned = HELMET_SEO.sub("", html_text)
    cleaned = re.sub(r"<head>", lambda _: "<head>\n" + head_html(m, site), cleaned, count=1, flags=re.I)
    noscript = ('<noscript><div style="max-width:880px;margin:0 auto;padding:32px 20px;font-family:system-ui,sans-serif;line-height:1.6">%s%s</div></noscript>'
                % (m["body"], nav))
    return re.sub(r"</body>", lambda _: noscript + "</body>", cleaned, count=1, flags=re.I)


def nav_links(base: str) -> str:
    return ('<nav><a href="%s/">Home</a> · <a href="%s/products.html">Products</a> · <a href="%s/catalogues.html">Catalogues</a> · <a href="%s/about.html">About</a> · '
            '<a href="%s/contact.html">Contact</a> · <a href="%s/privacy-policy">Privacy</a> · <a href="%s/cookie-policy">Cookies</a> · '
            '<a href="%s/terms">Terms</a></nav>') % ((base,) * 8)


# ----------------------------------------------------------------------------- share images

FONT_PATH = Path(__file__).parent / "fonts" / "Geist-Medium.ttf"


def _font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception:
        return ImageFont.load_default(size)


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def share_image(site_dir: Path, title: str, kicker: str, meta: str, photo: Optional[str]) -> bytes:
    """1200x630 card: product/collection photo on the right, name and branding on the left."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (239, 239, 239))
    PW = 600
    if photo:
        try:
            src = Image.open(site_dir / photo).convert("RGB")
            r = max(PW / src.width, H / src.height)
            src = src.resize((int(src.width * r) + 1, int(src.height * r) + 1), Image.LANCZOS)
            x0, y0 = (src.width - PW) // 2, (src.height - H) // 2
            img.paste(src.crop((x0, y0, x0 + PW, y0 + H)), (W - PW, 0))
        except Exception:
            pass
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 10, H], fill=(0, 166, 91))
    try:
        icon = Image.open(site_dir / "icon-192.png").convert("RGBA").resize((64, 64))
        img.paste(icon, (64, 56), icon)
    except Exception:
        pass
    d.text((148, 62), "SAP", font=_font(34), fill=(28, 28, 28))
    d.text((148, 100), "A Quality Product", font=_font(18), fill=(103, 104, 104))
    d.text((64, 190), kicker.upper(), font=_font(20), fill=(0, 166, 91))
    tf = _font(58)
    lines = _wrap(d, title, tf, 470)[:4]
    y = 232
    for ln in lines:
        d.text((64, y), ln, font=tf, fill=(28, 28, 28))
        y += 70
    if meta:
        d.text((64, y + 14), meta, font=_font(24), fill=(103, 104, 104))
    d.text((64, H - 70), TAGLINE, font=_font(22), fill=(60, 61, 61))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=86, optimize=True)
    return buf.getvalue()
