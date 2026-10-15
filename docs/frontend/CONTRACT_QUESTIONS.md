# Frontend integration questions

The authoritative plan and the supplied design spec have been read. `docs/contracts/` contains only `.gitkeep`; no OpenAPI or response schemas were published when frontend implementation began. The UI display types are provisional presentation models, not an API contract. No backend or ML files were edited.

## Backend

1. Does each bin carry trustworthy polyline geometry and explicit unsampled stretches? Supply actual per-point GPS, time and accuracy separately; the browser must not fabricate these from bin vertices.
2. Publish the live polling interval, staleness threshold and authoritative stale flag, capture/process times, connection state, camera profile and frame counters.
3. Which report fields are guaranteed: limitations, inspection actions, evidence references, fallback flag, model ID, version, export URL? How is a report retrieved after creation?
4. Are evidence layers signed image URLs, separate masks, vector shapes or composites? Supply expiry, dimensions, transforms, scale source, pattern/legend semantics and refresh behavior.
5. Publish maximum upload bytes, accepted formats, allocation request/response, exact presigned upload method/headers, finalize payload, job reference, typed errors and authorization/CSRF rules.
6. Is Stop and discard supported? It is omitted until documented. Supply session create/frame/finish schemas and transport arrangement; browser camera preview alone would not prove calibrated road capture.
7. Publish reason-code enumeration and retry semantics.
8. Publish session selection and sample/report listing or explicit entry links. The plan's minimum API has no listing endpoints; the frontend will not invent them.
9. Publish the complete OpenAPI document with `info.version`, health response and server compatibility version. Generate pinned client types using `npm run contract:generate -- <path> <version>` from `web/`; then implement the verified adapter.
10. Provide Maps browser key with site/API restrictions and billing readiness. No key is checked in. Expose only the key and API base URL to the browser.
11. Define route length coverage versus unique strip area and how overlap uncertainty is represented. Define signed evidence/export URL renewal and allowed origins.

## ML

1. Supply mask names, exact class definitions, available overlay geometry and denominator for every area.
2. Supply supported minimum chip diameter and gap width per camera profile and estimator version.
3. Supply score status, threshold labels/values, review policy and condition; no thresholds are computed in the UI.
4. Supply available confidence components and allowed descriptive states. No probability is invented.
5. Which ravelling/bleeding/polishing review flags are returned, with what reviewer provenance?
6. Define extent, gap IQR/p90, valid sample count, uncertainty, reference comparison and per-feature validity/null reasons. Supply histogram bins and supported lower limit before a distribution chart is connected.
7. Provide verified inclination value/unit/source/time/uncertainty/zero-check fields and optional input contract. No browser derivation or speculative input form is enabled.

## Client / organizer

1. The supplied design spec includes coral `#E5694F` for Bad and amber `#E3B04B` for Review. Implemented as functional condition semantics only; confirm or provide replacements.
2. Urbanist and Geist are implemented as specified; confirm any alternate brand font assets.
3. A Lucide route glyph is used as a provisional RoadSight wordmark symbol; supply an approved mark if different.
4. Confirm whether moving live capture is mandatory and minimum accepted speed. Live-camera access, calibrated detail, Indian transfer and grade remain visibly unverified.

## File-name resolution

The request names `docs/frontend/DESIGN_SPEC.md`; the actual file is `ROADSIGHT_DESIGN_SPEC.md`. The existing file is used directly and preserved. The repository name Ghost-Rider does not change the RoadSight product name requested by the plan.
