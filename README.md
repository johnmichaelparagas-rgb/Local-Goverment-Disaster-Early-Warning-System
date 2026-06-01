# Leyte DEWS — LGU Incident Reporting & Hazard Management System

A **Django + Django REST Framework** portal for **Municipal Disaster Risk Reduction &
Management Offices (MDRRMO)** in Leyte. It combines:

- A **server-rendered management UI** (Django session auth) for logging incidents with
  multiple hazard images via **inline formsets**, and a **django-filter** dashboard.
- A **JWT-secured REST API** for mobile/web clients, with **field-level masking** of
  dispatcher contact information for unauthenticated (public) consumers.
- A **JWT single-page monitoring dashboard** for hazard sensors, bulk status updates, and
  early-warning broadcasts.
- **Strict role-based access control** (LGU Admin / Dispatcher / Public Viewer) backed by
  Django Groups & Permissions, and **django-axes** brute-force defense.

---

## Quick start

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py setup_roles        # create role Groups + permissions (also run by seed)
python manage.py seed_demo          # demo accounts, sensors, incidents, images, a warning
python manage.py runserver
```

| URL                | What                                                              |
| ------------------ | ---------------------------------------------------------------- |
| `/`                | Public landing page (live public situation snapshot)             |
| `/dashboard/`      | JWT single-page monitoring dashboard (sensors, bulk, warnings)   |
| `/login/`          | Session login for the management UI                              |
| `/manage/`         | Incident dashboard — filtering + pagination                      |
| `/manage/incidents/new/` | Log incident + multiple images (inline formset, LGU Admin) |
| `/admin/`          | Django admin (LGU Admin only)                                    |
| `/api/...`         | REST API (see below)                                             |

### Demo accounts / roles

| Username     | Password         | Role          | Capabilities                                              |
| ------------ | ---------------- | ------------- | --------------------------------------------------------- |
| `admin`      | `Admin@2024`     | LGU Admin     | Full CRUD on incidents/images, user management, Django admin |
| `dispatcher` | `Dispatcher@2024`| Dispatcher    | View + update incident **status**; no create/delete, no user mgmt |
| `viewer`     | `Viewer@2024`    | Public Viewer | Read-only access to public-safe data                      |

---

## 1. Data model & UI — inline formsets

- `Incident` is the primary record; `HazardImage` is a related one-to-many model.
- [core/forms.py](core/forms.py) builds `HazardImageFormSet` with
  `inlineformset_factory(Incident, HazardImage, extra=3, can_delete=True, min_num=0)`.
- At `/manage/incidents/new/` an LGU Admin logs **one incident and attaches N images in a
  single submit**. Images are optional. Uploads are handled with `enctype="multipart/form-data"`.
- Each `HazardImage.save()` generates a **300×300 thumbnail** with Pillow, displayed in the
  editor and detail views.

## 2. Dashboard — advanced filtering

- [core/filters.py](core/filters.py) defines `IncidentFilter` (django-filter) with
  **date range** (`start`/`end` date pickers over `reported_at`) + **status** +
  municipality + type — all composable via querystring.
- `/manage/` renders the filter form and a **paginated** table (10/page), preserving active
  filters across pages, e.g.
  `/manage/?start=2026-05-01&end=2026-05-31&status=in_progress&municipality=Palo`.
- The same `IncidentFilter` powers the REST API via DRF's `DjangoFilterBackend`.

## 3. Security — strict RBAC + brute-force defense

- **Three roles**, mirrored as Django **Groups** with model **Permissions**
  (see [core/management/commands/setup_roles.py](core/management/commands/setup_roles.py)):
  - *LGU Admin* — full CRUD on incidents/images/sensors/warnings + user management.
  - *Dispatcher* — view + update incidents (status), no create/delete, no user management.
  - *Public Viewer* — read-only.
- Enforced by **custom DRF permission classes**
  ([core/permissions.py](core/permissions.py): `IncidentPermission`, `IsLGUAdmin`,
  `IsEditorOrReadOnly`) **and** by gating in the server-rendered views/templates.
- **django-axes** provides active brute-force defense: lock after
  `AXES_FAILURE_LIMIT` (default **5**) failed attempts per **username + IP**, with a
  **15-minute cool-off** and `AXES_RESET_ON_SUCCESS`. Lockouts return a clean **429**
  (JSON for the API, an HTML page for the browser).
  - Admin reset: `python manage.py axes_reset` /
    `python manage.py axes_reset_username <name>` / `axes_reset_ip <ip>`.

## 4. API — DRF + JWT + field masking

JWT via **djangorestframework-simplejwt**:

| Method | Path                   | Notes                                  |
| ------ | ---------------------- | -------------------------------------- |
| POST   | `/api/token/`          | Obtain `{access, refresh}`             |
| POST   | `/api/token/refresh/`  | Refresh an access token                |
| POST   | `/api/token/verify/`   | Verify a token                         |
| POST   | `/api/auth/login`      | Convenience login → `{token, user}` (axes-protected) |

**Resource endpoints** (`IncidentViewSet`, `HazardImageViewSet`, plus sensors/warnings):

| Method        | Path                          | Role                                   |
| ------------- | ----------------------------- | -------------------------------------- |
| GET           | `/api/incidents/`             | Public (masked) — filterable           |
| POST / DELETE | `/api/incidents/`             | LGU Admin only                         |
| PUT / PATCH   | `/api/incidents/{id}/`        | Dispatcher or Admin                    |
| GET/POST      | `/api/hazard-images/`         | upload via multipart; `?incident=<id>` |
| GET           | `/api/sensors/`, ...          | see monitoring API                     |

**Field-level masking** — `IncidentSerializer.to_representation`
([core/serializers.py](core/serializers.py)) inspects `request.user`:

- **Unauthenticated / Public Viewer:** `dispatcher_name`, `dispatcher_phone`,
  `dispatcher_email` are returned as `"[redacted]"`, and reporter PII / internal notes are
  dropped entirely.
- **Authenticated Dispatcher / LGU Admin:** all contact fields are returned in full.

```bash
# Public (masked) vs authenticated (full) on the SAME endpoint:
curl http://localhost:8000/api/incidents/                       # dispatcher_name: "[redacted]"
curl -H "Authorization: Bearer <access>" http://localhost:8000/api/incidents/   # full contact info
```

A separate, fully-masked read-only public API also exists for mobile home screens:
`/api/public/situation`, `/api/public/sensors`, `/api/public/warnings`, `/api/public/incidents`
(coarsened coordinates, no PII; optional `X-API-Key` gate via `PUBLIC_API_KEYS`).

---

## Architecture

```
dews_portal/        Project (settings, URLs, WSGI/ASGI)
accounts/           Custom User with roles + Group sync
core/
  models.py         Incident, HazardImage (thumbnails), Sensor, Reading, Warning, AuditLog
  forms.py          IncidentForm + HazardImageFormSet (inlineformset_factory)
  filters.py        IncidentFilter (django-filter: date range + status + ...)
  serializers.py    Internal + masked serializers; dynamic field masking
  permissions.py    Custom DRF permission classes (RBAC)
  axes_handlers.py  429 lockout response
  views.py          DRF viewsets, JWT login, bulk-status, public API
  web_views.py      Session-auth management UI (formset, dashboard)
  urls.py           API routing (+ SimpleJWT token endpoints)
  management/commands/  setup_roles, seed_demo
templates/          dashboard.html (SPA) + manage/*.html (formset, dashboard, login)
static/             css/js for both UIs
media/              uploaded hazard images + thumbnails (dev)
```

## Role / credential testing checklist

1. **Masking:** `GET /api/incidents/` unauthenticated → `dispatcher_*` redacted; with a JWT → visible.
2. **RBAC:** dispatcher `POST /api/incidents/` → **403**; admin → **201**; dispatcher
   `PATCH .../{id}/` status → **200**.
3. **Formset:** sign in as `admin`, open `/manage/incidents/new/`, attach 2+ images, submit →
   one incident with thumbnails.
4. **Filtering:** `/manage/?status=in_progress&municipality=Pastrana` plus date range.
5. **Brute force:** POST `/login/` with wrong password ≥5× → **429** lockout page; reset with
   `python manage.py axes_reset`.

## Production notes

- Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, real `DJANGO_ALLOWED_HOSTS`; swap SQLite for PostgreSQL.
- Serve `media/` and run `collectstatic`; serve `staticfiles/` via the web server.
- Tighten `CORS_*` to your app origins and require `PUBLIC_API_KEYS`.
- Configurable: `AXES_FAILURE_LIMIT` (env).
```
