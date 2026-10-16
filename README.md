# SAP Hardware — website + client admin

The redesigned site, unchanged visually, now driven by PostgreSQL with an admin panel at **/admin**.

| Piece | What it is |
|---|---|
| `site/` | The approved design (HTML/CSS/JS). Only the data source changed: pages read categories, products, slides etc. from the database instead of hardcoded lists. |
| `app/` | FastAPI server: serves the site, the public data, the enquiry form endpoint and the admin API. |
| `app/admin/` | The admin panel (plain HTML/JS, no build step). |
| `docker-compose.yml` | `web` + `db` (PostgreSQL 16). No host ports published. |

## What the client can control

- **Categories** — add, rename, describe, hide, reorder, set the hover image.
- **Products** — add, edit, hide, delete, reorder; photos (auto-resized), gallery, finishes, material, catalogue pages, variants, "New" badge.
- **Home page** — hero slides (add/replace/reorder/hide), featured products, catalogue cards, product/collection counters (automatic).
- **Enquiries** — contact-form submissions are saved; mark handled, export CSV.
- **Contact details** — display centres and offices.
- **Settings** — change password, edit finish colours.

## After first deploy: set up these in Admin

1. **Settings → Enquiry emails** — add the sending mailbox (for Gmail use smtp.gmail.com, port 587 and an *App password*) and the addresses that should receive enquiries. Use "Send a test email".
2. **Settings → Google & search** — paste the Google Analytics 4 ID and Search Console verification code once the real domain is live. Analytics loads only for visitors who accept cookies.
3. **About & legal** — review the founder page and the Privacy / Cookie / Terms texts (they are drafts; have them checked by your legal adviser).
4. **Downloads** — add catalogue PDFs as Google Drive links with a cover picture.
5. **Contact details** — paste a Google Maps link for each display centre.

SEO is automatic: every page gets its own title, description, canonical URL, Open Graph / Twitter tags, structured data (Organization, Product, Breadcrumb, LocalBusiness), a generated 1200x630 share image, `/sitemap.xml` and `/robots.txt`.

## Deploy on Coolify (Hostinger VPS)

1. Push this folder to a **private** Git repo (GitHub/GitLab).
2. Coolify → *Projects* → **+ Add** → new project `sap-hardware` (separate from your existing projects).
3. *+ New Resource* → *Docker Compose* (from the Git repo) → pick the repo, branch `main`, compose file `/docker-compose.yml`.
4. *Environment Variables*: set `POSTGRES_PASSWORD` (letters+digits), `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
5. Under the `web` service set **Domains** to `https://your-domain.com:8000` (the `:8000` is the container port). Point the domain's DNS A record at the VPS IP.
6. **Deploy.** First start creates the tables, loads the 70 products / 8 categories from the design, and creates the admin login.
7. Open `https://your-domain.com/admin`.

Backups: the two named volumes (`sap_pgdata`, `sap_uploads`) hold everything. In Coolify, schedule a backup of the database and keep the uploads volume in your VPS snapshots.

## Run locally

```bash
cp .env.example .env   # edit values
docker compose up --build
# site: needs a published port locally, e.g. add `ports: ["8000:8000"]` to web in a docker-compose.override.yml
```

## Notes

- Admin sessions are signed cookies (14 days). Login is rate-limited (8 tries / 10 min / IP).
- Uploaded images are converted to WebP and capped at 2000px.
- The server keeps one worker on purpose (in-memory rate limiting + 30 s content cache; admin edits invalidate it instantly).
- Static copy that is not a list (headlines, About-page story, footer social links) is still edited in `site/*.html`.
