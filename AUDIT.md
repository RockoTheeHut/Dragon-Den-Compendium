# Dragon Den Compendium — Project Audit

**Date:** 2026-06-12
**Commit:** `4524d83` (branch `main`, clean tree)
**Scope:** Full read-only audit — security, backend/Django correctness, frontend (templates/JS/CSS/accessibility), DevOps, testing, and documentation. No code was changed.
**Method:** Every Python file, all 42 templates, `app.js`, `styles.css`, Docker/Caddy/CI config, and the README were read and every finding below was verified against the actual code (file:line references included). The full test suite was executed in a throwaway venv.

---

## Executive Summary

This is a well-built hobby project — noticeably above average. Test discipline is real (88 tests, all passing, ~80% statement coverage, meaningful assertions), object-level access control in the per-user apps (games, tracker, notes) is consistently correct with no IDOR found, CSRF handling is flawless across all 42 templates, there is zero `|safe`/`autoescape off`/DOM-XSS exposure, and the Docker setup (multi-stage build, non-root drop, healthcheck, smoke-test CI, hardened prod overlay) is more rigorous than most production deployments of this size.

The serious issues cluster in four places:

1. **The prod compose overlay likely cannot start.** `cap_drop: ALL` removes the capabilities the entrypoint needs to `chown` and `gosu`-drop privileges, and CI never tests the prod overlay.
2. **CI never runs the test suite.** 88 passing tests exist; no workflow executes them.
3. **A developer `.env` gets baked into every Docker image.** `.dockerignore` doesn't exclude it and `COPY . .` picks it up.
4. **The XML import pipeline is fragile under concurrency and restarts** — duplicate objects, jobs stuck `RUNNING` forever, and tens of thousands of autocommit writes against SQLite.

There are no Critical security findings. The single most impactful product issue outside ops is that **any logged-in user can edit the shared global compendium** that all other users' games depend on.

### Scorecard

| Area | Grade | One-liner |
|---|---|---|
| Security | **B+** | Strong fundamentals (CSRF, XSS, access control, no secrets in git); gaps are hardening defaults and the shared-compendium edit policy |
| Backend correctness | **B** | Clean tenancy and ORM hygiene; concurrency (imports, turn tracker) is the weak spot |
| Frontend | **B−** | Excellent htmx discipline and CSRF; modals fail keyboard/a11y, ~390 lines of inline JS, heavy duplication |
| DevOps / Docker | **B** | Genuinely hardened design, but the prod overlay is likely broken and untested in CI |
| Testing | **A−** | 88 green tests, 80% coverage, behavior-asserting; CI doesn't run them |
| Documentation | **B+** | README is accurate (verified claim-by-claim); no LICENSE despite "open source" claim |

### Verified test run

```
88 tests, 0 failures, 0 errors — 10.95s  (manage.py test, Django 5.2.8, in-memory SQLite)
Statement coverage (apps only): 80%  (3,484 statements / 709 missed)
Weakest: compendium/rules.py 59%, text_utils.py 61%, compendium/views.py 62%, games/views.py 63%
Best:    notes/views.py 93%, import command 89%
```

---

## High-Priority Findings

### H1. Prod compose overlay very likely fails to start (`cap_drop: ALL` vs root entrypoint)
**`docker-compose.prod.yml:7-8`, `docker/entrypoint.sh:4-9`, `Dockerfile` (no `USER`)**

The image starts as root and the entrypoint must `chown -R app:app` (requires `CAP_CHOWN`) and `exec gosu app:app` (requires `CAP_SETUID`/`CAP_SETGID`). The prod overlay drops **all** capabilities, so these fail and `set -e` exits → restart loop (`restart: always` masks it as a crash loop). CI's smoke test supports `USE_PROD_OVERLAY=1` (`scripts/docker_smoke_test.sh:18-20`) but only ever runs the base compose, so this path has never been exercised.

**Fix:** Either `cap_add: [CHOWN, SETUID, SETGID]`, or (cleaner) set `USER app` in the Dockerfile, pre-create/chown the volumes at build time, and delete the root/gosu dance entirely. Then run the smoke test with `USE_PROD_OVERLAY=1` in CI.

### H2. CI never runs the test suite
**`.github/workflows/` — only `docker-smoke.yml` and `perf-guard.yml`**

88 passing tests exist and the suite takes ~11 seconds, but nothing in CI executes `manage.py test`. A regression that breaks every test would merge green.

**Fix:** Add a workflow job: setup-python → `pip install -r requirements.txt` → `python manage.py test`.

### H3. Developer `.env` (secrets) gets baked into Docker images
**`.dockerignore` (missing `.env`), `Dockerfile:39` (`COPY . .`), `dragon_den/settings/base.py:28` (auto-loads `.env`)**

Any image built on a machine with a local `.env` ships `SECRET_KEY` and `OPENAI_API_KEY` inside the image layers, and settings auto-load it at runtime. Also missing from `.dockerignore`: `dnd.xml` (12 MB) and `docs/` — pure image bloat.

**Fix:** Add `.env`, `dnd.xml`, `docs/`, `.github/` to `.dockerignore`.

### H4. XML import: concurrent runs create duplicate GameObjects
**`compendium/management/commands/import_fightclub_xml.py:392-417`, `compendium/models.py:43-47`, `core/import_jobs.py:15`**

The importer does check-then-create (`filter(...).first()` then `create(...)`) with no `UniqueConstraint` on `(system, object_type, external_id)` and no transaction — and the `ThreadPoolExecutor(max_workers=2)` explicitly allows two imports to run simultaneously. Both threads pass the existence check; both insert.

**Fix:** Add the unique constraint (after a dedupe data migration) and switch to `update_or_create` / `bulk_create(ignore_conflicts=True)`.

### H5. Import jobs die silently on restart and stay `RUNNING` forever
**`core/import_jobs.py:15, 83-87`; surfaced at `core/views.py:113-120`**

Jobs run in an in-process thread pool. A deploy, gunicorn worker recycle, or crash mid-import leaves the job row `PENDING`/`RUNNING` permanently — no startup recovery, no timeout, no stale-job sweep — and the UI shows an "active import job" forever. There is also no claim step, so a job could in principle execute twice.

**Fix:** Claim jobs with a conditional `UPDATE ... WHERE status='pending'`, and mark stale `RUNNING` jobs failed at startup. Longer-term: a management-command worker or real queue.

### H6. Import pipeline is non-transactional: tens of thousands of autocommits on SQLite
**`import_fightclub_xml.py:381-431`, `dragon_den/settings/base.py:91-96`**

Each XML element issues 2–3 separate autocommit statements; a full Fight Club file (thousands of elements) means tens of thousands of individually fsync'd SQLite write transactions holding the global write lock, contending with live web requests. A crash mid-loop leaves a half-imported compendium with no record of what landed.

**Fix:** Wrap the import in `transaction.atomic()`, prefetch existing objects for the file's external IDs in bulk, and batch creates.

---

## Security

No Critical findings. CSRF, XSS, object-level access control, and secrets hygiene were all checked in depth and came back clean (see Strengths).

### Medium

- **S1. Any authenticated user can edit/overwrite the shared global compendium.** `compendium/views.py:50-60` (`object_create`), `:79-90` (`object_edit`) enforce only `@login_required` — no ownership or role check — while the tag views (`:131`, `:171`) *do* enforce ownership. One user can silently rewrite the `data` JSON of monsters every other user's games and tracker rely on. (Tempered by tracker entries snapshotting monster data at add time.) **Fix:** mirror the tag rules — track `created_by` on `GameObject` and restrict editing of `OFFICIAL`/`IMPORTED` objects to staff.
- **S2. XML parsed with `xml.etree.ElementTree`, not `defusedxml`.** `import_fightclub_xml.py:4`, `:372`. Any authenticated user can upload arbitrary XML (`core/views.py:152`), exposing entity-expansion DoS ("billion laughs"). Stock ElementTree doesn't resolve external entities, so classic XXE file-read is not in play — the practical risk is memory/CPU exhaustion. **Fix:** `import defusedxml.ElementTree as ET` (drop-in) and add `defusedxml` to requirements.
- **S3. OpenAI API keys encrypted with a key derived from `SECRET_KEY`, which defaults to a known dev value.** `core/models.py:22-25` derives a Fernet key from `SHA256(SECRET_KEY)`; `settings/base.py:36` falls back to `"dev-only-secret-key-change-me"` unless `REQUIRE_STRONG_SECRET_KEY=1` (off by default, not set in dev compose). Stored keys are trivially decryptable under the default, and rotating `SECRET_KEY` silently wipes every stored key (decrypt returns `""`, `core/models.py:43-45` — no warning). **Fix:** default `REQUIRE_STRONG_SECRET_KEY` to true when `DEBUG` is off; use a dedicated `FIELD_ENCRYPTION_KEY` env var so secret rotation doesn't destroy data.

### Low

- **S4. No rate limiting or lockout on login/signup; registration is open.** `core/views.py:59`, `dragon_den/urls.py:5`. Permits credential brute-forcing and automated account creation. **Fix:** `django-axes` or `django-ratelimit`; consider an invite gate.
- **S5. Unset `DJANGO_SETTINGS_MODULE` falls back to `DEBUG=True`.** `wsgi.py:14`/`asgi.py:14` default to `settings.local`; `settings/__init__.py` re-exports `local` too. Production safety depends entirely on compose setting `.base`. A misconfigured deploy serves full tracebacks. **Fix:** make the non-debug module the default; dev opts in.
- **S6. `SECURE_PROXY_SSL_HEADER` trusted unconditionally.** `settings/base.py:142` always trusts `X-Forwarded-Proto`, while the dev compose publishes gunicorn on `0.0.0.0:8000` (`docker-compose.yml:7`) — a direct client can spoof the header to bypass `SECURE_SSL_REDIRECT`. **Fix:** env-gate it; bind the dev compose to `127.0.0.1`.
- **S7. HSTS disabled by default even in prod.** `settings/base.py:146` and `docker-compose.prod.yml:26` both default `SECURE_HSTS_SECONDS` to `0`; the Caddyfile doesn't set it either. **Fix:** set `31536000` once HTTPS is confirmed stable.

### Verified clean (worth knowing)

- **CSRF:** every state-changing view uses `@require_POST`; every POST form in all 42 templates includes `{% csrf_token %}`; the JS autosave fetch sends the token with `credentials: "same-origin"`.
- **XSS:** zero `|safe` / `autoescape off` in templates; `compendium/rules.py` builds its `mark_safe` HTML exclusively via `escape()`/`format_html()` (verified line-by-line); the only data-driven `innerHTML` interpolates `parseInt`-sanitized numbers; `|escapejs` used where names enter inline JS.
- **IDOR:** every games/tracker/notes query scopes by `user=request.user` or `_is_game_owner` + `get_object_or_404(..., game=game)`, including form querysets. No cross-user leak found.
- **Secrets:** no `.env`, keys, or database committed or in git history; `.gitignore` covers them.
- **File uploads:** chunked writes to `NamedTemporaryFile`, cleanup in `finally`, user input never controls the import path — no traversal.
- **Prod hardening intent:** non-root drop, `no-new-privileges`, loopback bind, secure cookies, SSL redirect, `REQUIRE_STRONG_SECRET_KEY=1` in the prod overlay (see H1 for the caveat that the overlay likely doesn't boot).
- **Dependencies:** all 5 pins current with no known outstanding CVEs as of audit knowledge (Django 5.2.8 LTS, gunicorn 23.0.0, cryptography 45.0.6, whitenoise 6.9.0) — but see D4 on patch staleness.

---

## Backend Correctness & Code Quality

### Medium

- **B1. `GET /tracker/?encounter=abc` returns a 500.** `tracker/views.py:284-286` passes the raw query string into `filter(pk=...)` → `ValueError` on non-numeric input. The sibling helper `_get_active_encounter` (`:70-75`) parses defensively; `dashboard` doesn't. **Fix:** same try/except, return the existing `HttpResponseBadRequest`.
- **B2. `save_magic_item_global` 500s on malformed payload.** `utilities/views.py:177` does `json.loads` on a user-editable hidden field; `MagicItemSaveGlobalForm` (`utilities/forms.py:65-66`) lacks the `clean_generated_payload` its sibling form has (`:83-92`). **Fix:** shared base form.
- **B3. `GameObjectInstance.base_object` uses `on_delete=CASCADE`, defeating the snapshot design.** `games/models.py:24`. The model exists to be an independent per-game copy, but deleting the base object (e.g. `remove_user_imported_xml`, `core/views.py:263-266`) cascades and destroys the per-game copies. **Fix:** `SET_NULL` (nullable FK) or `PROTECT`.
- **B4. `remove_user_imported_xml` is non-atomic (TOCTOU).** `core/views.py:248-266` — count, delete mappings, delete objects as three autocommit steps; a concurrent import in the window loses its mapping. The legacy fallback (`:230-241`) deletes **all** `source=IMPORTED` objects server-wide. **Fix:** `transaction.atomic()` + re-validate inside.
- **B5. `sort_order` allocation races.** `tracker/views.py:322-326`, `:346`, `:377` (and `:271`) all do `aggregate(Max(...))` then save inside `transaction.atomic` — which doesn't serialize concurrent adds. Duplicate sort orders corrupt drag-and-drop ordering (SQLite's single-writer lock mostly masks it; Postgres wouldn't). The idiom is also copy-pasted four times. **Fix:** `select_for_update()` in one shared helper.
- **B6. Turn-advance read-modify-write races on `is_current`.** `tracker/views.py:526-555`, `:561-578`, `:490-496`. Two rapid "next turn" posts can skip turns; on Postgres both can commit and trip the partial unique constraints (`tracker/models.py:47-58`) → 500. The constraints are good defense; the views should lock. **Fix:** `select_for_update()` inside the existing atomic blocks.
- **B7. Active encounter lives in one session key — two tabs corrupt each other.** `tracker/views.py:17, 69-91`. Every mutation resolves the encounter from the shared session; a DM with two tracker tabs has all writes land on whichever encounter was opened last, and `clear_entries` (`:584-586`) can wipe the wrong one. `dashboard` also clears the active encounter on a plain GET (`:290-291`) — a GET side effect. **Fix:** carry the encounter id in URLs/hidden fields; session only as default.
- **B8. Related-reference detection scans every GameObject in the system per detail render.** `compendium/rules.py:57-60` pulls all objects of 8 types and substring-scans in Python. The 1-hour cache (`compendium/detailing.py:36-55`) mitigates, but it's per-process `LocMemCache` (no `CACHES` configured) — each gunicorn worker re-does it cold. **Fix:** precompute a name→id table at import time, or configure a shared cache.

### Low

- **B9. Admin registrations are dead code** — all five `admin.py` files register models but `django.contrib.admin` isn't in `INSTALLED_APPS` and no admin URL exists. `SharedNoteQuerySet.visible_to` (`notes/models.py:11-15`) has zero call sites. Wire up or delete.
- **B10. Duplicated logic that will drift:** attack extraction re-implemented in `tracker/views.py:131-159` vs `compendium/text_utils.py:224-234`; the import upsert loop duplicated (`import_fightclub_xml.py:316-350` vs `:392-431`); the owner-gate boilerplate repeated in 10 games views (a decorator or `Game.objects.for_user(user)` queryset would collapse it).
- **B11. Exceptions swallowed without logging; no `LOGGING` config anywhere.** `core/import_jobs.py:68-73` stores `str(exc)` and discards the traceback; `utilities/views.py:153` similar. Add `logger.exception(...)` and a basic LOGGING config.
- **B12. Scratchpad uniqueness not enforced.** `notes/views.py:12-31` documents "exactly one per user" but uses filter-then-create; concurrent first requests create a duplicate that lingers forever. Conditional `UniqueConstraint` + `get_or_create`.
- **B13. Importer name-fallback merges distinct objects** (`import_fightclub_xml.py:398-406` — same-named monsters from different books collapse, second overwrites first) and `findall(f".//{tag}")` (`:382`) matches at any nesting depth.
- **B14. Magic item generator: synchronous OpenAI call in the request cycle, no POST-redirect-GET.** `utilities/views.py:138-154` — refresh re-issues a paid generation call and a slow API call ties up a gunicorn worker.
- **B15. Settings nits:** `USE_TZ = False` (`base.py:116`) stores naive datetimes; temp upload files leak if job creation raises after the file is written (`core/views.py:173-194`).

### Strengths

- Tenancy filtering is consistently correct across every view and form queryset checked.
- Deliberate `select_related`/`prefetch_related`/`.only()` usage, bulk updates for reordering, paginated lists — ORM hygiene is above average.
- Good constraints where it matters: partial unique `is_current` per user/encounter, unique favorites, unique tags, unique import mappings.
- Cache keys include `updated_at` (correct invalidation); `deepcopy` on cache read avoids cross-request mutation.
- Deterministic content-hash external IDs give the import real idempotency groundwork.

---

## Frontend (Templates, JS, CSS, Accessibility)

### High

- **F1. Modals have no keyboard support.** ~14 modal instances (`base.html:100-148`, `tracker/dashboard.html:18-66`, `games/game_detail.html:57-162`, `game_list.html:22`, preview shell) are plain divs with click-outside-to-close only: no Escape, no focus trap, no `role="dialog"`/`aria-modal`, no body scroll lock, no focus restore. Keyboard users can tab into the obscured page and cannot dismiss. **Fix:** one shared modal component wired into the existing `openAppModal`/`closeAppModal` (`base.html:214-250`).
- **F2. ~390 lines of inline `<script>` in `base.html` (lines 155-542)** plus more in `game_detail.html:164-258` and `game_list.html:41-61` — uncacheable, re-parsed every load, invisible to manifest hashing. Only 5 `{% url %}` values tie it to the template; emit those as `data-url-*` attributes and move it all to a static module.
- **F3. The same 8-line modal open/close wrapper is written ~13 times** (`app.js:193-263`, ×10 in `game_detail.html`, ×2 in `game_list.html`). A single delegated handler on `data-modal-open`/`data-modal-url` attributes deletes ~200 lines and most of the 54 inline `onclick=` handlers (which also block any future CSP).

### Medium

- **F4. Hardcoded URLs in JS** — `app.js:214-251` and `:438` build `/tracker/...`/`/compendium/...` paths by string concat; `game_detail.html:194,213,239` uses the `{% url ... 0 %}".replace("/0/", ...)` hack. URL changes break silently. Put resolved URLs in `data-url` attributes.
- **F5. No user-facing error state for failed requests.** The only `htmx:responseError` handler (`base.html:520-532`) just hides the import spinner; a failed "Advance Turn" or save gives zero feedback. The scratchpad autosave (`base.html:294-306`) has `.catch(function () {})`, never checks `response.ok`, and fires as the modal closes — silent note loss. The `.messages` toast UI already exists (`base.html:85-94`) — wire a global error handler to it.
- **F6. CDN scripts without SRI, render-blocking, one major version behind.** `base.html:23-24` loads htmx 1.9.12 and SortableJS from unpkg with no `integrity`/`crossorigin`/`defer`. Self-host via whitenoise or add SRI + defer.
- **F7. Topbar overflows on phones** — `flex-wrap` only exists in the 961-1180px block (`styles.css:2513-2535`); at 400px the menu button, search, and 4 actions share one non-wrapping row. The mobile drawer also never closes on navigation and has no backdrop (`app.js:69-84`).
- **F8. Component duplication:** favorite button partial exists (`compendium/partials/favorite_button.html`) but is inlined separately in `object_rows.html:4-9` and `home.html:43-46` (the latter shows a stale ⭐ after htmx swaps); condition `<select>` repeated 4×; ability-score grid repeated in 5 templates; `entry_row.html` + `entry_card.html` both render for every tracker entry with CSS hiding one — double DOM, and they've already drifted (row has `aria-label`s, card doesn't).
- **F9. CSS variable discipline:** `--focus-ring` defined but used once while `rgba(80,181,255,0.2)` appears 16× and `#6fb4e6` 9×; 13 `!important`s fighting hardcoded shadows in theme-light overrides; sticky offsets (`top: 72px/66px/84px/44px`) magic-coupled to topbar height — use a `--topbar-height` var.
- **F10. Accessibility gaps:** user-chosen tag colors with fixed `#111` text (`styles.css:752` + 5 templates) → ~2:1 contrast on dark picks (compute text color from luminance server-side); unlabeled search/filter inputs (`object_list.html:11-31`) and status-effect form fields; tab buttons in a `role="tablist"` lack `role="tab"`/`aria-selected`; favorite toggle conveys state only via emoji (add `aria-pressed`).
- **F11. 512×512 PNG nav icons (~222 KB) rendered at 20×20** (`static/icons/`). Resize/convert for ~95% savings.

### Low

- **F12.** Dead CSS verified unused: `.note-card`, `.settings-divider`, `.grid-form`, `.dice-result-pop`, `.random-item-result-pop`, `.compendium-reference-*`, and `.search-preview-list li a` rules targeting anchors that are now buttons.
- **F13.** Fake POST form to open the settings modal (`base.html:72-75`) — should be `<button type="button">`.
- **F14.** Manual cache-bust `?v=phase2-polish-38` (`base.html:22,154`) — hand-bumped, redundant in prod where manifest storage hashes.
- **F15.** Static `<title>` while `hx-push-url` rewrites history — every history entry reads the same.
- **F16.** Compendium body class set from JS pathname (`app.js:16-19`) → first-paint background flash; render it server-side.
- **F17.** `login.html` extends base while `signup.html` is a bare partial through `render_page` — two different shells for near-identical pages.
- **F18.** `input[type="number"] { color-scheme: dark }` (`styles.css:2392`) leaks dark spinners into the light theme.

### Strengths

- CSRF discipline is flawless; htmx used consistently with real progressive-enhancement fallbacks, server-side debounce, OOB swaps, and `hx-trigger="revealed"` infinite scroll.
- Idempotent JS binding (`data-*Bound` guards) prevents duplicate listeners across swaps.
- Real responsive design: table→card swap at 760px, sidebar drawer at 960px, `prefers-reduced-motion` honored in CSS *and* JS.
- `:focus-visible` styles on virtually every interactive element; nav icons correctly `alt="" aria-hidden="true"`.
- Loading/skeleton states exist (import progress modal, htmx-request button styling, infinite-scroll row).
- Prod static caching correctly delegated to whitenoise `CompressedManifestStaticFilesStorage`.

---

## DevOps, Testing & Documentation

(H1–H3 above are the top items in this area.)

### Medium

- **D1. Large untested surfaces** (matching the coverage gaps): the entire signup flow; `object_create`/`object_edit`/`toggle_favorite`/`quick_search_redirect`/tag creation/list filtering in compendium; `delete_game`/`delete_encounter` and all success paths for player/instance mutations in games; manual `add_entry`, `edit_entry` POST, `remove_entry`, `set_current`, `clear_entries`, and all four status-effect mutations in tracker; `save_magic_item_global` and the (mockable) generation call in utilities. No cross-user isolation test exists for tracker entries — the views filter correctly today, but nothing locks that in. ~560 statements of parsing logic in `rules.py`/`text_utils.py` have no direct unit tests.
- **D2. Startup perf guard writes to the production database.** `docker/entrypoint.sh:35-38` runs `scripts/perf_guard.py` against the live SQLite on every boot (warn-only, but it bulk-creates ~320 rows + a user and relies on `finally` cleanup — a SIGKILL strands them in real data). The CI variant (`perf-guard.yml`) gates on wall-clock thresholds (160/180/35 ms) on shared runners — inherently flaky. **Fix:** point it at a scratch `SQLITE_PATH`; in CI gate on query counts/bytes, not milliseconds.
- **D3. SQLite + 3-4 gunicorn workers without WAL or busy timeout.** `settings/base.py:91-96` sets no `OPTIONS`; concurrent writes risk `database is locked` 500s. **Fix:** Django 5.1+ `init_command` for WAL + `timeout`.
- **D4. Dependency management:** 5 exact pins, no dev/test split, no lockfile, no Dependabot/Renovate. Django 5.2 LTS is a good choice (supported ~April 2028) but the patch level (5.2.8) is stale as of mid-2026, and `cryptography==45.0.6` (mid-2025) is security-sensitive and likely behind advisories. **Fix:** `.github/dependabot.yml` + bump patch versions.
- **D5. README claims "open source" but there is no LICENSE file** — default all-rights-reserved. Add one.
- **D6. `.env.example` incomplete** — missing `REQUIRE_STRONG_SECRET_KEY` (which the README's own production checklist calls required) and `COMPENDIUM_IMPORT_ASYNC`.

### Low

- **D7.** 12 MB `dnd.xml` committed at repo root (next-largest tracked file is 76 KB) — release asset or LFS candidate.
- **D8.** `.gitignore` minimal — lacks `.coverage`, `.pytest_cache/`, editor dirs, `*.log`, `compendium_xml/*.xml`.
- **D9.** No `HEALTHCHECK` in the Dockerfile (compose-only).
- **D10.** Caddyfile is correct and minimal; no HSTS/CSP/Permissions-Policy headers (HSTS delegated to Django env — fine but split-brained; see S7).
- **D11.** Some tests assert brittle markup/JS strings (e.g. `tracker/tests.py:86` asserting an `onclick` string) — template refactors will break them without behavior changes.
- **D12.** Git history: 27 commits with messages like "Stuff", "I Dont Know", "Did a lot" — fine for a solo project, worth tightening if collaborators join.

### Strengths

- Tests are genuinely behavior-asserting: ownership/403 checks across apps, snapshot-isolation tests, idempotent-import tests with stable external IDs, edge cases (truncation, validation, history limits), and performance-regression guards. Zero assertion-free or flaky tests found; full suite ~11s.
- Docker setup is above-average: multi-stage build, slim base, venv copy, privilege-drop design, compose healthcheck against a real `/healthz/`, dedicated smoke-test script wired into CI, hardening-minded prod overlay.
- `scripts/perf_guard.py` (per-route latency + max-query-count + payload budgets with fixture cleanup) is a genuinely good idea — it would catch most N+1 regressions on hot paths; it just needs a scratch DB and non-wall-clock CI gates.
- README verified accurate claim-by-claim against settings, entrypoint, compose, and URLs.

---

## Prioritized Remediation Roadmap

**Do first (deployment-breaking / secret exposure / CI blind spots):**
1. Fix or test the prod overlay capability drop (H1) and run the smoke test with `USE_PROD_OVERLAY=1` in CI.
2. Add a CI test job (H2) — ~11s of runtime buys regression coverage for 88 tests.
3. Add `.env` (plus `dnd.xml`, `docs/`) to `.dockerignore` (H3).

**Do soon (data integrity / security hardening):**
4. Harden the import pipeline: unique constraint + `update_or_create`, `transaction.atomic()`, job claiming + stale-job recovery (H4–H6).
5. Restrict editing of shared compendium objects (S1) and switch the snapshot FK off CASCADE (B3).
6. Swap to `defusedxml` (S2 — one-line change) and enforce a strong `SECRET_KEY` whenever `DEBUG` is off (S3/S5).
7. Fix the two user-triggerable 500s (B1, B2) and enable SQLite WAL + busy timeout (D3).

**Quality-of-life (next refactor pass):**
8. Shared modal component with keyboard support (F1/F3) and extract inline JS to a static module (F2).
9. `select_for_update` helpers for sort-order and turn-advance races; explicit encounter id instead of session-only (B5–B7).
10. Surface request errors to users + fix the silent scratchpad autosave (F5); add LICENSE (D5); add Dependabot (D4); point perf guard at a scratch DB (D2).

---

*Audit performed by Claude Code (Fable 5) via four parallel specialized review agents (security, backend, frontend, DevOps/testing) with cross-verification of high-impact findings against source. All file:line references verified at commit `4524d83`. No code was modified; the only file added is this report.*

---

# Remediation Log — 2026-06-12

All changes below were applied the same day as the audit, with the full test suite green after each batch (suite grew from 88 to 125 tests, all passing). The Docker prod overlay fix was verified by actually booting the image under the hardened flags.

## High-priority items — all fixed

| ID | Status | What was done |
|---|---|---|
| H1 | ✅ Fixed & verified | Added `cap_add: [CHOWN, SETUID, SETGID]` to the prod overlay; CI smoke test now runs a base/prod matrix. Verified live: image built and booted under `cap_drop: ALL` + those caps — migrations, gosu privilege drop, and `/healthz/` all clean. |
| H2 | ✅ Fixed | New `.github/workflows/tests.yml` runs `manage.py check` + the full suite on every push/PR. |
| H3 | ✅ Fixed | `.dockerignore` now excludes `.env`/`.env.*`, `dnd.xml` (12 MB), `docs/`, `.github/`, caches. |
| H4 | ✅ Fixed | Partial `UniqueConstraint` on `(system, object_type, external_id)` with a dedupe data migration (duplicates keep their rows, later ones get `external_id` blanked — no FK breakage). |
| H5 | ✅ Fixed | Jobs are claimed atomically (`UPDATE … WHERE status='pending'`); `reap_stale_jobs()` fails PENDING/RUNNING jobs older than 2h, invoked from the settings context. |
| H6 | ✅ Fixed & measured | Importer rewritten: two-pass parse, bulk prefetch, `bulk_create`/`bulk_update`, one transaction. Real `dnd.xml` (6,444 objects) imports in 1.3 s; re-import is fully idempotent (0 created / 6,444 unchanged). |

## Security

- **S1 Fixed** — `GameObject.created_by` added (migration); `object_edit` now allows staff for anything, creators (or legacy unowned) for CUSTOM only; the edit form is hidden without permission. Magic-item saves also set ownership.
- **S2 Fixed** — `defusedxml` swap (in requirements + importer).
- **S3 Fixed** — `REQUIRE_STRONG_SECRET_KEY` now defaults ON whenever `DEBUG` is false (placeholder keys abort startup); optional `FIELD_ENCRYPTION_KEY` decouples stored-key encryption from `SECRET_KEY` rotation; failed decrypts now log a warning instead of failing silently.
- **S4 Fixed** — per-IP rate limiting on login (`ThrottledLoginView`, 10/5 min) and signup (5/hour) via a cache-backed fixed-window counter (`core/throttle.py`).
- **S5 Fixed** — WSGI/ASGI default to `settings.base`; `settings/__init__.py` is intentionally empty so a mispointed `DJANGO_SETTINGS_MODULE` fails loudly instead of silently running DEBUG.
- **S6 Fixed** — `SECURE_PROXY_SSL_HEADER` is now gated behind `TRUST_PROXY_SSL_HEADER` (off by default, on in the prod overlay); dev compose binds to `127.0.0.1` by default.
- **S7 Fixed** — prod overlay defaults `SECURE_HSTS_SECONDS=31536000`.

## Backend

- **B1/B2 Fixed** — both user-triggerable 500s (non-numeric `?encounter=`, malformed magic-item payload) now return 400; payload validation lives in a shared form base class.
- **B3 Fixed** — `GameObjectInstance.base_object` → `SET_NULL` (migration), so deleting base objects no longer destroys per-game snapshots.
- **B4 Fixed** — `remove_user_imported_xml` wrapped in `transaction.atomic`; the legacy server-wide wipe is now staff-only.
- **B5/B6 Fixed** — SQLite now runs WAL + 20 s busy timeout + `transaction_mode=IMMEDIATE`, which serializes all `transaction.atomic` writers at BEGIN — eliminating the sort-order and turn-advance races on this SQLite-only app. The four copy-pasted max-sort blocks collapsed into one `_next_sort_order()` helper.
- **B7 Fixed** — tracker mutations accept an explicit `encounter_id` (now emitted as a hidden input by every tracker form), so two tabs on different encounters no longer clobber each other through the session; session remains the fallback. Foreign/stale ids → 404.
- **B8 Improved** — production now uses a cross-process file-based cache so per-object render caching survives across gunicorn workers (full precompute-at-import deferred).
- **B9 Fixed** — Django admin enabled (`/admin/`) instead of deleting the five registration files — it now backs the staff workflows added in S1/B4; the unused `visible_to` queryset was removed.
- **B10 Fixed** — tracker attack extraction now delegates to the canonical `compendium.text_utils.extract_monster_attacks`; the 11 games ownership gates collapsed into `_get_owned_game_or_forbidden()`.
- **B11 Fixed** — `LOGGING` config added; import-job and generation failures now `logger.exception`/`warning`.
- **B12 Fixed** — scratchpad uses `get_or_create` backed by a unique constraint (+ dedupe migration).
- **B13 Fixed** — importer matches only direct children of the XML root, and the name-match fallback only repurposes `IMPORTED` rows — a user's same-named custom object can no longer be overwritten by an import.
- **B14 Fixed** — magic-item generation is POST-redirect-GET (session-stored result); refresh no longer re-bills.
- **B15 Fixed** — `USE_TZ=True` (note: timestamps stored before this change were naive local times and will display shifted); temp upload files are cleaned up if job creation fails.

## Frontend

- **F1 Fixed** — modal manager (`static/base.js`) now centrally provides Escape-to-close, Tab focus trap, focus restore, `role="dialog"`/`aria-modal`/`aria-labelledby`, and body scroll lock for every modal in the app.
- **F2 Fixed** — all ~390 lines of inline `<script>` in base.html extracted to `static/base.js`; the four `{% url %}` dependencies became `data-url-*` attributes on `<body>`. Scripts load `defer` from `<head>`.
- **F3 Fixed** — both games templates' inline script blocks (12 wrapper functions) deleted in favor of delegated `data-modal-open/-close/-url/-content` and `data-action-url/-modal-title` handlers in app.js. The `{% url … 0 %}".replace()` hack is gone (F4 for games). Tracker's `openTracker*Modal` globals were deliberately kept.
- **F5 Fixed** — global `htmx:responseError`/`sendError` toasts (reusing the `.messages` UI); scratchpad autosave now checks `response.ok` and warns the user on failure instead of silently dropping notes.
- **F6 Fixed** — htmx 1.9.12 and SortableJS 1.15.3 self-hosted under `static/vendor/` (no CDN, no SRI needed), loaded with `defer`.
- **F7 Fixed** — topbar wraps below 960 px; the mobile drawer closes on navigation and on outside tap.
- **F8 Partially fixed** — home page now reuses the favorite-button partial (stale-⭐ bug gone). Condition-select / ability-grid / entry row+card dedup deferred.
- **F10 Partially fixed** — tag pills compute black/white text from background luminance (new `tag_text_color` filter, applied in all 5 templates); favorite button has `aria-pressed` + state-aware `aria-label`; compendium filters have `aria-label`s. Tab roles deferred.
- **F11 Fixed** — nav icons resized 512→64 px (222 KB → 20 KB).
- **F12 Fixed** — the ten verified-dead CSS rule blocks removed.
- **F13/F14/F16/F18 Fixed** — settings opener is a plain button; manual `?v=phase2-polish-38` cache-bust strings dropped (manifest storage handles prod); `is-compendium-page` rendered server-side (no first-paint flash); number-input `color-scheme: dark` scoped to the dark theme.
- **Deferred:** F9 (CSS variable consolidation), F15 (per-page titles), F17 (login/signup shell unification), entry row/card merge (F8b).

## DevOps / Testing / Docs

- **D1 Fixed** — 36 new tests covering signup (+throttle), compendium create/edit permissions, favorites, search redirect, list filters, tag creation, tracker mutations + cross-user isolation + explicit-encounter semantics, games success paths, magic-item save/generation (mocked OpenAI), and stale-job reaping. Suite: 125 tests, ~15 s, green.
- **D2 Fixed** — startup perf guard runs against a throwaway scratch DB (never the live one); CI perf guard uses the new `--skip-timing` flag so it gates only on query counts and payload bytes. Budgets adjusted for the (intentional) `BEGIN IMMEDIATE` query and encounter-id payload cost.
- **D3 Fixed** — WAL + busy timeout + IMMEDIATE transactions (see B5/B6).
- **D4 Fixed** — Django 5.2.8→5.2.15, gunicorn 23→26, cryptography 45→48, whitenoise 6.9→6.12, openai 2.17→2.41, defusedxml added; `.github/dependabot.yml` (pip/actions/docker, weekly).
- **D5 Fixed** — MIT LICENSE added (swap it if you prefer another license).
- **D6/D8/D9 Fixed** — `.env.example` rewritten (all missing vars, key-generation hint); `.gitignore` extended; Dockerfile `HEALTHCHECK` added.
- **README updated** throughout to match (admin/staff model, env vars, importer guarantees, overlay caps, CI list, license).
- **Deferred:** D7 (`dnd.xml` still tracked in git — moving it to a release asset/LFS rewrites history; it is at least excluded from Docker images now), D11 (brittle markup assertions in old tests), D12 (commit message hygiene going forward).

## Verification summary

- `manage.py test`: **125/125 OK** (~15 s)
- `manage.py check` + `makemigrations --check`: clean
- Real-data import: 6,444 objects in 1.3 s, idempotent on re-run
- Perf guard (query/byte budgets): all three routes PASS
- Prod-overlay container boot (cap_drop ALL + minimal cap_add): healthy, serving
- Render smoke: 16 routes 200/302, explicit-encounter flows correct
