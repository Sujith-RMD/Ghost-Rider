# Ghost-Rider — project skeleton setup instructions

Give this file to the AI that initializes the repository **before** giving the three role files to their respective AIs. The authoritative scope and technical choices are in `final_plan.md`; copy that document into `Ghost-Rider/docs/final_plan.md` during setup. This file specifies structure and ownership only. Do not implement the application, train a model, download datasets, create cloud resources, or invent measurements during skeleton setup.

## 1. Inputs and output

Inputs are the existing `final_plan.md` and the three files `BACKEND_AWS_ROLE.md`, `ML_ROLE.md`, and `FRONTEND_ROLE.md`. Read the final plan, especially Sections 1–2, 4–5, 11–16, and 18. Create one project directory named `Ghost-Rider`. Put all ongoing **human-authored Markdown work documents** under `Ghost-Rider/docs/`. The project root `README.md` is the entry-point exception required by Section 16 of the final plan. Generated data reports and exports can live in `reports/` in their actual output formats; their explanatory Markdown belongs in `docs/`. The final plan's Member A and Member B responsibilities are combined in the requested ML role; its Member C responsibilities are split between backend/AWS and frontend. This changes ownership, not project scope.

Do not move or overwrite the supplied source plan. Copy it into the new repository for collaborators. Keep the source copy outside the repository untouched.

## 2. Create this skeleton

```text
Ghost-Rider/
  README.md                       # brief entry point pointing to docs/final_plan.md
  pyproject.toml                  # minimal project metadata; no guessed dependencies
  configs/
    camera/                      # ML-owned calibration/geometry profiles
    features/                    # ML-owned measurement and data mappings
    scoring/                     # ML-owned reference and SQI policy
    deployment/                  # backend-owned runtime configuration
  backend/
    __init__.py
    schemas.py                   # backend-owned shared Pydantic contracts
    ingestion/                   # backend: upload/live/replay adapters and timestamps
    quality/                     # ML: validity and supported-domain checks
    geometry/                    # ML: calibration, scale, transforms, uncertainty
    aggregate/                   # ML: classical/learned masks and measurements
    distress/                    # ML: segmentation and physical extent
    reference/                   # ML: known-good profiles and comparisons
    scoring/                     # ML: SQI and deterministic reasons
    routes/                      # backend: grouping, coverage and segment summaries
    reports/                     # backend: structured facts, Bedrock wrapper, exports
    api/                         # backend: FastAPI, authorization, durable jobs
  web/                           # frontend: React, TypeScript, Vite, Google Maps
  training/                      # ML: reproducible Colab and training code
  data_manifests/                # ML: provenance, parent groups, frozen splits
  annotation_guides/             # ML: machine-readable annotation assets only
  eval/                          # ML: CV and Indian/live acceptance evaluation
  tests/
    backend/                     # backend tests
    ml/                          # ML tests
  infra/                         # backend: Docker and one EC2 deployment path
  reports/
    backend/                     # backend-generated exports, non-Markdown
    ml/                          # ML-generated metrics and plots, non-Markdown
  demo/                          # backend-owned approved demo assets and replay backup
  docs/
    README.md                    # copy of this documentation-folder policy
    final_plan.md                # copy of the supplied final plan
    PROJECT_SKELETON_SETUP.md   # copy of this file
    BACKEND_AWS_ROLE.md         # copy of backend role file
    ML_ROLE.md                  # copy of ML role file
    FRONTEND_ROLE.md            # copy of frontend role file
    contracts/                  # backend-owned interface and schema documentation
    backend/                    # backend work notes, runbooks, cost/infra notes
    ml/                         # data admission, annotation guide, feature/scoring specs, validation
    frontend/                   # UI behavior, states, Maps integration, accessibility notes
    decisions/                  # numbered cross-role decisions; backend maintains index
```

This extends the Section 16 tree only where the user requested a `docs/` home and where separate ownership prevents simultaneous edits. It does not introduce another service, model, data source, product feature, or requirement.

Create `__init__.py` only where needed for Python package imports. Use `.gitkeep` for otherwise empty directories that Git must retain; do not create placeholder production logic, fake model weights, sample scores, generated OpenAPI files, or fabricated validation results. Add appropriate `.gitignore` entries for raw images, private GPS, downloaded archives, weights, local databases, keys, and generated artifacts. Include no credentials. A lockfile is added only after a tested environment exists, as the final plan requires.

The root `README.md` should only tell collaborators what Ghost-Rider is, how to find `docs/final_plan.md`, and which role document to read. The setup AI must not choose the camera, exact Bedrock model ID, calibrated thresholds, final score bands, or paid AWS instance size.

## 3. Ownership rules to establish at setup

All three roles may **read** the whole repository and run checks against it. Only the owning role may **write** its code/config/test/report area. A role must not silently edit another role's files to fix an integration problem; instead, record the requested contract change in its own `docs/<role>/` area and coordinate with the owner. The final plan is read-only for all three role AIs unless the user directs a revision.

| Area | Writer |
|---|---|
| `backend/schemas.py`, `backend/ingestion/`, `routes/`, `reports/`, `api/`; `infra/`; `configs/deployment/`; `tests/backend/`; `reports/backend/`; `demo/`; root `README.md` and `pyproject.toml` | Backend & AWS AI |
| `backend/quality/`, `geometry/`, `aggregate/`, `distress/`, `reference/`, `scoring/`; `training/`; `data_manifests/`; `annotation_guides/`; `eval/`; `configs/camera/`, `features/`, `scoring/`; `tests/ml/`; `reports/ml/` | ML AI |
| `web/` including its own frontend tests and package configuration | Frontend AI |
| `docs/contracts/` and `docs/decisions/` index | Backend & AWS AI maintains; other roles request changes in their own docs |
| `docs/backend/`, `docs/ml/`, `docs/frontend/` | The named role only |
| `docs/final_plan.md`, `docs/README.md` and the four setup/role instruction files | Read-only reference copies for all roles |

The backend owns the shared schema and HTTP contract. The ML AI defines scientific fields and statuses in a proposal under `docs/ml/`, then the backend incorporates an agreed version into `schemas.py` and `docs/contracts/`. The frontend consumes the published contract. This is a file-ownership rule, not permission for the backend to redefine units or scoring on its own.

`annotation_guides/` exists because the final plan names it; put hand-written annotation instructions and review records in `docs/ml/`, and use `annotation_guides/` for structured export templates or machine-readable class mappings. Put hand-written deployment and validation reports in the appropriate `docs/` subfolder even when the corresponding raw CSV/JSON/plots are generated under `reports/`.

## 4. First interface to agree before parallel implementation

Have the role AIs align on the final plan's canonical record and minimum API in Sections 11.4–11.5. The backend publishes a versioned Pydantic/OpenAPI contract covering:

- identity/source lineage, timestamps and camera/calibration IDs;
- GPS provenance, accuracy, route distance and simulated-versus-real status;
- geometry validity, observed area, scale source and uncertainty;
- quality status (`accepted`, `limited`, `rejected`) and reason codes;
- each metric's value, unit, validity status and estimator version;
- score as value-or-null, Good/Bad/review/unknown state, reference and policy version;
- job lifecycle and typed error states;
- image/overlay evidence references, Bedrock narrative status and segment coverage.

`null` means not measured/unknown; zero means measured absence. A missing scale cannot become mm, cm² or count/m². A missing GPS cannot become an Indian map coordinate. Upload, live and replay use the same analysis record, with source mode shown honestly.

Until that contract is published, frontend may use clearly labeled typed mock payloads and ML may use a local adapter for prototype measurements. Neither should invent a conflicting permanent schema.

## 5. Setup completion check

Before handing off to the three AIs, verify that every directory in the tree exists, the documentation-folder policy, four instructions and final plan are copied under `docs/`, the root README points to them, ownership is unambiguous, there are no secrets or fabricated outputs, and a simple Python package import can work without implementing project behavior. Hand each collaborator its role file together with read access to `docs/final_plan.md` and `docs/contracts/`.
