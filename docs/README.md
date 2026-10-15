# Ghost-Rider Documentation

This directory contains all human-authored Markdown work documents for the Ghost-Rider project.

## Documentation Structure

### Core Documents
- `final_plan.md` - Authoritative project scope and technical choices
- `PROJECT_SKELETON_SETUP.md` - Repository setup instructions
- `BACKEND_AWS_ROLE.md` - Backend & AWS role responsibilities
- `ML_ROLE.md` - Machine Learning role responsibilities
- `FRONTEND_ROLE.md` - Frontend role responsibilities

### Role-Specific Work Areas

#### Backend Documentation (`docs/backend/`)
- Work notes, runbooks, cost/infrastructure notes
- Owned by: Backend & AWS AI

#### ML Documentation (`docs/ml/`)
- Data admission decisions, annotation guides
- Feature/scoring specifications, validation reports
- Owned by: ML AI

#### Frontend Documentation (`docs/frontend/`)
- UI behavior, states, Maps integration
- Accessibility notes
- Owned by: Frontend AI

#### Contracts (`docs/contracts/`)
- Backend-owned interface and schema documentation
- Versioned Pydantic/OpenAPI contracts
- Owned by: Backend & AWS AI (other roles request changes)

#### Decisions (`docs/decisions/`)
- Numbered cross-role decisions
- Index maintained by: Backend & AWS AI

## File Placement Guidelines

### Human-Authored Markdown → `docs/`
All hand-written `.md` work documents belong here:
- Design decisions
- Runbooks and procedures
- Validation reports (textual)
- Annotation instructions
- API documentation

### Generated Artifacts → `reports/`
Machine-generated outputs go to `reports/backend/` or `reports/ml/`:
- CSV/JSON exports
- Plots and metrics
- Performance benchmarks

Their *explanatory* Markdown still belongs in `docs/`.

### Machine-Readable Assets → Specific Directories
- `data_manifests/` - Dataset provenance and splits
- `annotation_guides/` - Structured export templates, class mappings

## Ownership Rules

All three roles may **read** any documentation. Only the owning role may **write** to their designated area.

To request a change in another role's area:
1. Document the exact requested change in your own `docs/<role>/` area
2. Coordinate with the owner
3. Never silently edit files you don't own

## Read-Only Documents

These documents are reference copies for all roles:
- `final_plan.md`
- `PROJECT_SKELETON_SETUP.md`
- `BACKEND_AWS_ROLE.md`
- `ML_ROLE.md`
- `FRONTEND_ROLE.md`

Changes to these require user direction.
