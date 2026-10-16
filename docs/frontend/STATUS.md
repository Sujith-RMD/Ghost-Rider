# RoadSight frontend status

**Phase 1 integration update (16 October 2026):** The production Assess screen now performs the real upload → finalize → job → sample workflow. Stored sample detail and live System health are also connected. Other production screens remain disconnected. See `PHASE1_INTEGRATION_REPORT.md` for evidence and limits; the older status below describes the pre-integration baseline.

**Current priority:** the user’s **1920 × 1080** desktop only. Existing mobile styles are left in place; further mobile/tablet refinement and their browser test are deferred.

## What is implemented

React 18, strict TypeScript and Vite app in `web/`, with Tailwind tokens, locally served Urbanist/Geist, React Router, TanStack Query, Zustand selection state, visx charts and a lazily loaded Google Maps component. The dark shell, ivory navigation, thin numerals, nested radii and condition glyphs/patterns follow the supplied `ROADSIGHT_DESIGN_SPEC.md`.

Implemented screens: Route map/distance fallback, Assess, Live/replay monitor, Samples, sample evidence detail, session summary, report list/detail and System. Evidence supports available-layer toggles, original/overlay comparison, opacity, native-pixel zoom, pan, pinch and keyboard controls, full-screen focus management and legends. Route bins, chart selection and evidence table share selection state. Unknown stretches remain neutral; the chart breaks at missing observations. Tablet evidence has peek/half/full sheet positions; mobile has five bottom tabs and a header System control. Long segment tables use measured-row virtualization above 200 rows.

Scientific values use the discriminated `Metric` presentation type. Measured zero, unknown, unsupported and pixels-only values have different output. Small nonzero areas retain significant digits. Score status and severe-defect inspection flags are independent. Reports render structured facts before supporting prose, identify template fallback, and expose unresolved references. All role-owned Markdown notes are in `docs/frontend/`.

## What is mocked

Development (`npm run dev`) and the explicitly named preview bundle (`npm run build:demo`) use synthetic fixtures, with a persistent non-dismissible mock banner. The geometric SVG surfaces and masks are schematic test assets, not captured road images, model predictions, physical calibration or Indian validation. Capture times, condition values and frame counters in preview mode are fixed fixtures. No coordinates are assigned to these schematic samples. Default route preview is explicitly simulated; `?fixture=no-gps` preserves the distance-only case. Simulated session geometry is synthetic and does not assign coordinates to schematic sample images. Without a working Maps key, a labeled abstract contour backdrop is shown.

Normal `npm run build` uses a disconnected, empty service adapter. It excludes fixtures, the preview banner and fixture assets; its bundling guard rejects imported mock modules or the banner string. It displays the integration dependency rather than invented measurements. This is a safe production shell, **not a connected production assessment system**.

## What is blocked

`docs/contracts/` has no published OpenAPI/schema. Real upload allocation/S3 transfer/finalize/polling, session transport/start/finish, real evidence adapters, report creation/retrieval/export, authoritative health, session selection and server-version comparison need that contract and backend service. Mutation buttons are disabled with explanations. Assess can select, decode and preview a real local JPEG/PNG, but does not pretend to analyse it. The job-state fixture control is a development-only custom panel, excluded from both built bundles.

Google Maps rendering, bin layers, controls, simulated-route labeling and integration error handling are implemented, but an authorized Maps key, billing and real GPS geometry have not been supplied or tested. Key/auth/billing errors and network errors stay in the integration family. Raw GPS/accuracy layers, histogram inputs and optional verified-grade entry require their scientific fields and metadata before connection. No camera, calibrated chip detail, grade measurement, Indian transfer or successful AWS/Bedrock integration is claimed.

The exact field and service requests, plus the supplied client questions, are in `CONTRACT_QUESTIONS.md`. Production connection must include replacing the provisional display adapter, generating/pinning real OpenAPI types, and exercising the actual services; merely setting an API base URL is insufficient.

## Running and handing off

From `Ghost-Rider/web`:

```text
npm ci
npm run dev
npm run typecheck
npm run lint
npm test
npm run build
npm run build:demo
npx playwright install chromium
npm run test:e2e
```

If using an already installed Chromium browser, `PLAYWRIGHT_CHROMIUM_EXECUTABLE` can point to its executable. For example in PowerShell, set it to the installed Chrome executable before running browser tests. The tests use port 5183; normal development defaults to 5173.

Only `VITE_API_BASE_URL` and a referrer/API-restricted `VITE_GOOGLE_MAPS_API_KEY` are browser configuration. Put local values in ignored `.env.local`; no AWS/Bedrock credentials belong here. When backend publishes its document:

```text
npm run contract:generate -- ../docs/contracts/openapi.json <exact-info.version>
```

This verifies `info.version` and writes generated types/version under `web/src/contract/`; it does not invent missing request/response semantics or automatically activate live operations.

## Verification

- Strict TypeScript, ESLint, Vitest honesty tests and normal production bundling checked.
- Browser suite exercises all nine screens at the confirmed 1920 × 1080 desktop target, checks no horizontal page overflow and runs axe against WCAG A/AA rules. Keyboard evidence controls, queued-versus-succeeded state, source filters, unsampled gaps, stale replay, template fallback, reduced motion and greyscale also checked.
- Desktop/mobile screenshots are in `docs/frontend/screenshots/`, with a greyscale route capture. Automated accessibility checks are evidence for the tested fixture states, not a certification of every future backend payload.
- Source and screenshot review removed extra route copy so coverage stays visible, corrected chart ARIA and mobile System labeling, fixed mobile evidence overflow and preserved native-pixel zoom semantics.

During setup, npm writes inside OneDrive failed with Windows EPERM. Dependencies were installed in a temporary workspace and copied into `web/node_modules`, then checks were run against the actual project. The tested lockfile is included. Future collaborators should use `npm ci`; if OneDrive interferes, use an ordinary local checkout rather than changing scientific or application behavior.

No backend, ML, root configuration, infrastructure or authoritative-plan files were edited.


## Desktop reference refinement

The reference-inspired 1920 × 1080 pass adds a full-bleed abstract/map canvas, glass coverage and distance cards, large thin metrics, image-led placeholder cards, a wider Assess layout and a slim mock banner. See DESIGN_REFINEMENT_REVIEW.md and screenshots/refinement/. Mobile work remains deferred.
