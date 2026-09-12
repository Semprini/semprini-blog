# semprini-blog — Claude Instructions

## What this is

`semprini.me` — a Wagtail 7.4 / Django 6 blog with **puput** grafted in as the blog engine,
plus a first-party `devcast` app adding dev-project pages, narrated audio posts and animated
diagrams.

Depends on the **semprini-core** stack (`/home/paul/Dev/semprini-core`) being up first: it owns
Traefik, Keycloak and the `semprini_internal` Docker network this stack joins as `external`.

> `semprini-core/CLAUDE.md` still says the host is Oracle Cloud ARM64. It is not — see below.
> Trust `semprini-core/docs/dns-records.md`.

## Deployment

**Host:** `ubuntu@3.107.254.151` — AWS Lightsail, `ap-southeast-2`, instance `semprini-core`,
x86_64. SSH by key, no `~/.ssh/config` entry needed. Traefik (from semprini-core) fronts it;
the web container binds `172.17.0.1:8000` only.

**The host is not a git checkout.** Code flows laptop → host by rsync:

```bash
./infra/sync-to-host.sh            # sync only, prints the follow-up commands
./infra/sync-to-host.sh --deploy   # sync, rebuild web+narrator, restart, wait for gunicorn
```

Then, **always**, because static is served from S3 and not by Django:

```bash
ssh ubuntu@3.107.254.151 'cd ~/semprini-blog \
  && docker cp semprini-blog-web-1:/app/static_collected/. data/static_collected/ \
  && python3 upload_static_s3.py'
```

### Five things that will catch you out

1. **Python deps come from `app/requirements.txt`, not `pyproject.toml`.** The Dockerfile
   `pip install -r /requirements.txt`. Adding a dependency to `pyproject.toml` alone changes
   nothing in the container — it must go in both.
2. **Static is served from S3**, `STATIC_URL=https://s3.ap-southeast-2.amazonaws.com/semprini.me/static/`.
   `collectstatic` runs at *image build* time into `/app/static_collected` inside the container.
   Nothing publishes it. New JS/CSS 404s in the browser until the `docker cp` + `upload_static_s3.py`
   above is run. `data/static_collected/` on the host is the staging copy the uploader reads.
3. **Migrations run in the container's CMD**, so `docker compose up -d web` applies them. That
   makes a restart a schema change. **Take a dump first:**
   ```bash
   ssh ubuntu@3.107.254.151 'docker exec semprini-blog-db-1 sh -c \
     "pg_dump -U \$POSTGRES_USER -d \$POSTGRES_DB" | gzip > ~/snapshots/semprini-blog-$(date -u +%Y%m%dT%H%M%SZ).sql.gz'
   ```
4. **The host is authoritative for secrets and data.** `.env.prod`, `.env.prod.db`,
   `data/postgres18_data/`, `data/media/`, `data/backup/` are excluded from the sync. Pushing
   the laptop's copies over them reverts rotated credentials or destroys live data.
5. `manage.py check` reports **8 pre-existing treebeard/puput warnings**. They are not yours.

### Verifying a deploy

```bash
ssh ubuntu@3.107.254.151 'cd ~/semprini-blog && docker compose ps \
  && docker exec semprini-blog-web-1 python manage.py showmigrations devcast | tail -3'
curl -s -o /dev/null -w "%{http_code}\n" https://semprini.me/
```

## Architecture

- **puput graft.** `devcast.conf.page_base()` resolves `DEVCAST_PAGE_BASE` to
  `puput.models.EntryPage`, so devcast page types inherit the blog's URLs, feeds, archives and
  comments. This is set before the first migration and cannot change afterwards.
- **`devcast` is written to be extractable** into `wagtail-devcast`. It reads settings only
  through `devcast/conf.py` and never imports `semprini`, `feedback` or `search` directly.
  Keep it that way. See `docs/devcast-design.md` §10.
- **Blocks carry a narration contract.** Every block in `devcast/blocks.py` implements
  `narration_text()`, returning what a speech engine should read or `""` to be skipped. A new
  block that omits it silently breaks the audio pipeline.
- **Narration audio is rendered by the `narrator` container**, not in the request cycle. It is
  the only process holding `ELEVEN_LABS_API_KEY`.

### Rich text vs StreamField — this matters

puput `EntryPage` bodies are **Draftail rich text**, not StreamFields. Existing blog posts
(entry 69 and friends) therefore **cannot host a StreamField block**. Anything that must be
insertable into an ordinary post has to be a **rich text embed type**, the way images are:
`<embed embedtype="diagram" id="3"/>`, registered in `devcast/wagtail_hooks.py`.

Only `AudioEntryPage.sections` and `DevProjectPage.showcase` are StreamFields.

## Diagrams (animated draw.io exports)

Designed in `docs/devcast-design.md` §6; validated by the trial in `examples/data-architecture/`
whose `FINDINGS.md` is the reference for anything UI-shaped.

- `devcast/svgtools.py` — sanitise → strip raster labels → pin colour scheme → wrap camera group
  → index. Runs once on `Diagram.save()`, never at render time.
- **Uploaded SVG becomes live DOM** in a logged-out reader's browser (it has to be inlined to be
  animatable). The sanitiser is an allowlist over a parsed tree — never regex over a string, and
  never at render time.
- `app/static/js/diagram.js` — one paused GSAP timeline per figure, playhead driven from
  outside. GSAP is fetched from cdnjs only when a page actually has an animated diagram.
- Load a diagram (there is no script editor yet):
  ```bash
  manage.py import_diagram <file.svg> --title "..." --model <file.drawio> --page <PageName> --script <script.json>
  ```

**Outstanding:** the Draftail chooser (`devcast/static/devcast/js/diagram-chooser.js`) is the one
piece never exercised in a browser — registration, chooser URL and the contentstate round trip
are verified server-side only. There is no editor for the animation script. Animating
"Data Products E2E" in entry 69 needs an SVG export of it; the post currently has a PNG
(image 84) and that diagram is not in `Data_Architecture.drawio`.

## Local development

SQLite by default, so no containers needed:

```bash
cd app && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver
```

Point at a scratch database with `SQL_DATABASE=/tmp/x.sqlite3` rather than using `app/db.sqlite3`,
which is a real local dev database.

The 3D avatar is generated, not hand-modelled — `data/blender_scripts/build_avatar.py` rebuilds
`semprini_avatar.glb` from `data/Semprini.blend`. `data/Semprini_sculpt.blend` is a terminal
branch for hand-sculpting and is *not* regenerable from it.

## Key docs

- `docs/devcast-design.md` — the design for both devcast content types and §6 diagrams
- `examples/README.md` and `examples/data-architecture/FINDINGS.md` — the diagram trial
- `../semprini-core/docs/dns-records.md` — the authoritative host/IP record
- `../semprini-core/CLAUDE.md` — the core stack, its networks and startup order
