# RoadSight AI: frontend design specification

Audience: the coding agent that builds `web/**`. Read this together with `docs/FRONTEND_ROLE.md`, `docs/final_plan.md` and `docs/contracts/`. If this file and the final plan disagree on a scientific field, unit, endpoint or status, the final plan and the published contract win. If they disagree on how something looks, this file wins.

Place this file at `docs/frontend/DESIGN_SPEC.md`. It is a hand-written Markdown note, so it belongs in `docs/frontend/`, not in `web/`.

---

## 0. The product in one paragraph

RoadSight AI measures road-surface condition from images. A user uploads a still, starts a live camera session, or replays a recording. A backend worker runs quality, geometry, aggregate/distress analysis, reference comparison and scoring, then returns a sample record with evidence images, measured values, a condition state and reasons. Samples are grouped into 50 m route bins and drawn on Google Maps. A report combines stored facts with a Bedrock-written narrative.

The interface is a **dashboard for an inspector**. The inspector's job is to decide whether to trust a conclusion, so every screen exists to let them compare the image, the overlay and the measured numbers. The design must never look more certain than the data.

**The one memorable thing** in this design: the route line on the map is drawn only where we actually measured. Unsampled stretches stay quiet and neutral, and the condition chart breaks where coverage breaks. Everything else stays calm so this honesty reads at a glance.

---

## 1. What we take from the reference, and what we drop

The reference is a dark fleet-management dashboard. We borrow its structure and finish, not its content.

### 1.1 Mechanisms to reproduce (the "bar")

These are checkable by looking. A reviewer should be able to confirm each one on a rendered screenshot.

1. **Two-zone shell.** A fixed left column of stacked cards (about 440 px) beside a full-bleed map. The map runs under the top navigation and under the floating cards.
2. **Pill navigation.** Tabs are text-only pills. The active tab is a solid ivory pill with ink text. Inactive tabs are ivory at 72% with no background.
3. **Large, light numerals.** Hero values use a thin geometric weight (200 to 300) at roughly 5x the label size. The decimal part and the unit are dimmed (secondary text colour) and smaller. Example: `78` in full ivory, `.3` and `%` dimmed.
4. **Glass over map.** Cards floating on the map use translucent ivory fill with a strong backdrop blur and a hairline border. Cards in the left column are solid surfaces, not glass.
5. **Nested radii.** Outer cards 24 px, inner tiles 16 px, chips fully round. Inner radius is always smaller than its container.
6. **Teal as signal only.** The accent marks live or healthy data, the active data series and the selected map element. It is never a decorative gradient or button wash. At most two teal elements are visible per card.
7. **Quiet chrome.** No drop shadows. Depth comes from surface lightness steps and the blur on glass.
8. **Dashed target line with highlighted points.** The line chart carries a dashed reference line and marks only the notable points with small filled dots.
9. **Small arrow-up-right glyph** in the top-right corner of every card that opens a detail view.
10. **Status chips are outlined**, small, sentence case, with a leading glyph.

### 1.2 Reference features we do NOT build

The reference shows fleet features that do not exist in this project. Do not add them, not even as disabled tabs or placeholder data.

- Vehicle-type filters (bus, taxi, train, tram), vehicle illustrations, route numbers, schedules, passenger load, "schedule offset", crew, maintenance, incidents, fleet, analytics.
- "Operational efficiency" or any invented KPI.
- User accounts, teams, notifications, settings pages beyond what the backend exposes.
- Repair cost estimates, pavement depth, binder thickness, certified roughness, structural condition, sieve gradation. The plan says these are not measured.
- Any inclination value derived in the browser.

### 1.3 Translation table

| Reference element | RoadSight element |
|---|---|
| Vehicle-type tabs with counts | Source-mode filter: `All`, `Live`, `Replay`, `Still`, each with a sample count |
| Online / Offline tiles | `Accepted` / `Limited` / `Rejected` quality tiles (three tiles, see 6.2) |
| Operational Efficiency chart | Condition along route distance, with line breaks where coverage is unknown |
| Vehicle cards with route thumbnails | Recent sample cards with the original image thumbnail, status chip, GPS accuracy chip |
| GPS / LTE chips | `GPS ±4 m` chip, `Live`/`Replay`/`Still` chip, `Calibrated`/`Uncalibrated` chip |
| Glass "Passenger Load" card on map | Selected-bin card: median condition, accepted samples, coverage |
| Schedule Offset table | Segment table: bin, distance, samples, strip area, median, lower tail, flags |
| Map zoom / locate pill | Same control group, plus a layer toggle |
| Map style picker ("Map 2") | Layer menu: route bins, raw GPS points, accuracy circles |

---

## 2. Design tokens

The three brand colours are fixed. Everything else is derived from them by mixing ivory into ink, so the whole UI stays in one tonal family.

### 2.1 Colour

```css
:root {
  /* Brand (fixed by the client) */
  --ink:        #031211;
  --ivory:      #E8E4D3;
  --teal:       #00AEBB;

  /* Surfaces: ivory mixed into ink */
  --surface-0:  #031211;   /* app background, map letterbox */
  --surface-1:  #0C1A19;   /* left-column cards (4% ivory) */
  --surface-2:  #152321;   /* nested tiles, inputs (8% ivory) */
  --surface-3:  #1F2B28;   /* hover, pressed, table row hover (12% ivory) */

  /* Lines */
  --line:       rgb(232 228 211 / 0.10);
  --line-strong:rgb(232 228 211 / 0.20);

  /* Text on dark */
  --text-1:     #E8E4D3;                    /* primary */
  --text-2:     rgb(232 228 211 / 0.72);    /* secondary */
  --text-3:     rgb(232 228 211 / 0.56);    /* tertiary: smallest allowed text colour (4.5:1) */

  /* Glass */
  --glass-fill: rgb(232 228 211 / 0.07);
  --glass-line: rgb(232 228 211 / 0.12);

  /* Accent roles */
  --signal:       var(--teal);                 /* live, healthy, selected data */
  --signal-soft:  rgb(0 174 187 / 0.16);
  --focus-ring:   var(--ivory);                /* 2px ring + 2px ink offset */
}
```

### 2.2 Condition colours (functional extension, not decoration)

Condition states need more than three colours. We add the minimum, used only for condition semantics (map bins, chips, legend, chart dots). **Never use them for buttons, backgrounds or decoration.** Flag this to the client in `docs/frontend/` so they can approve or change the two extra hues.

| State | Colour | Non-colour cue (mandatory) |
|---|---|---|
| Good | `--teal` `#00AEBB` | solid fill, check glyph |
| Bad | `#E5694F` | solid fill, cross glyph |
| Review | `#E3B04B` | diagonal-stripe fill, eye glyph |
| Unknown | `rgb(232 228 211 / 0.48)` | dotted hatch fill, question glyph |
| Unsampled (map only) | `rgb(232 228 211 / 0.22)` dashed line | no fill, no glyph, no tooltip claim |
| Severe observed defect flag | outlined diamond in `#E5694F`, independent of state | diamond glyph plus text "Inspect" |

Every condition state must be distinguishable in greyscale. Test this.

Good/Bad/Review thresholds are **not** designed here. They come from the published score policy in the API response. The UI never hardcodes 70, 40 or any other band.

### 2.3 Typography

Two families, clearly distinct.

- **Urbanist** (variable, 200 to 700): display numerals, page titles, card titles. Light and geometric, matching the reference's thin numerals.
- **Geist** (variable, 400 to 600) with `font-variant-numeric: tabular-nums`: body text, tables, units, tooltips, form controls.

Load both through `@fontsource-variable/*` with `font-display: swap`. Stacks: `Urbanist, "Avenir Next", system-ui, sans-serif` and `Geist, system-ui, sans-serif`.

| Token | Family | Size / line | Weight | Use |
|---|---|---|---|---|
| `display-xl` | Urbanist | 72 / 72 | 200 | Hero SQI number on sample detail |
| `display-l` | Urbanist | 56 / 56 | 200 | Hero numbers on left-column cards |
| `title-l` | Urbanist | 40 / 44 | 300 | Page titles ("Route condition") |
| `title-m` | Urbanist | 20 / 28 | 500 | Card titles |
| `body` | Geist | 14 / 22 | 400 | Default text |
| `body-s` | Geist | 13 / 20 | 400 | Table cells, chips |
| `caption` | Geist | 12 / 16 | 400 | Units, axis labels, provenance (never below 12 px) |

Rules:
- Sentence case everywhere. No all-caps labels, no tracked-out eyebrows.
- Decimal part and unit of a hero number render in `--text-2` at 40% of the integer size.
- Line length under 72 characters for narrative text.
- Do not accent a single word in a headline.
- Do not use monospace.

### 2.4 Spacing, radius, glass, elevation

- Spacing scale (px): 4, 8, 12, 16, 20, 24, 32, 48. Card padding 20. Gap between left-column cards 12. Gap inside a card 16.
- Radius: `--r-card: 24px`, `--r-tile: 16px`, `--r-input: 12px`, `--r-chip: 999px`.
- Glass recipe: `background: var(--glass-fill); backdrop-filter: blur(20px) saturate(1.1); border: 1px solid var(--glass-line); box-shadow: inset 0 1px 0 rgb(232 228 211 / 0.06);` Provide a solid `--surface-1` fallback inside `@supports not (backdrop-filter: blur(1px))`.
- No `box-shadow` for elevation. Never animate `backdrop-filter` or `filter`.

### 2.5 Iconography

Lucide icons at 16 px (inline) and 20 px (controls), stroke 1.5, colour inherited. Condition glyphs are custom SVG so they stay legible at 12 px.

---

## 3. Layout and responsive behaviour

### 3.1 Desktop shell (1280 px and up)

```text
+--------------------------------------------------------------------------------+
| logo  [Route map] Assess  Live  Samples  Reports  System           ● API ready |
+----------------------------+---------------------------------------------------+
| LEFT COLUMN (440, scrolls) |  MAP (full bleed, under header)                   |
|                            |  Route condition                                  |
| [All 412][Live 96]         |  [Session: Bangalore test 3 v]  [Layers v]        |
| [Replay 180][Still 136]    |                                                   |
|                            |                  ( glass: selected bin )          |
| [Accepted][Limited][Rejected]                                                  |
|                            |                                                   |
| Condition along route      |                                                   |
|  ~~~~~   ~~~~~~~           |   [+][locate][-]                                  |
|                            |  +---------------------------------------------+  |
| Recent samples (2 col)     |  | Segment table (collapsible bottom drawer)   |  |
+----------------------------+---------------------------------------------------+
```

- Header is 64 px, transparent over the map, blurs on scroll of the left column only.
- Left column is `surface-0` with 12 px outer padding; cards are `surface-1`.
- Right zone is the Google Map. The page title "Route condition" sits on the map at top-left in `title-l`, with a text shadow of none and a soft scrim (a 120 px linear gradient from `rgb(3 18 17 / 0.7)` to transparent) to keep it legible over bright satellite tiles.
- Bottom drawer shows the segment table. Collapsed height 56 px, expanded 40% of viewport.

### 3.2 Tablet (768 to 1279 px)

Left column becomes a bottom sheet with three snap points (peek 96 px, half, full). The map fills the screen. Navigation stays as top pills, horizontally scrollable.

### 3.3 Mobile (below 768 px)

Single column. Map is a 40vh block at the top of the Route map page; cards stack beneath. Navigation becomes a bottom tab bar with five items (Route map, Assess, Live, Samples, Reports). System health sits in a header overflow menu. Evidence overlays go full screen with a close control.

### 3.4 Other pages use the same shell

Pages without a map (Assess, Samples, Reports, System) keep the header and replace the map zone with a content zone on `surface-0`, max width 1120 px, left aligned. Do not centre-align content blocks. Left-align everything except numerals inside fixed-width tiles.

---

## 4. Information architecture and routes

| Route | Page | Backend source |
|---|---|---|
| `/` | Route map (default) | `GET /v1/sessions/{id}/segments`, `GET /v1/samples/{id}` |
| `/assess` | Upload a still and track it | `POST /v1/uploads`, `POST /v1/uploads/{id}/finalize`, `GET /v1/jobs/{id}` |
| `/live` | Live or replay session | `POST /v1/sessions`, `POST /v1/sessions/{id}/frames`, `POST /v1/sessions/{id}/finish`, `GET /v1/jobs/{id}` |
| `/samples/:id` | Sample detail with the evidence viewer | `GET /v1/samples/{id}` |
| `/sessions/:id` | Session summary (segments, coverage) | `GET /v1/sessions/{id}/segments` |
| `/reports/:id` | Report | `POST /v1/reports` and the report link it returns |
| `/system` | Health and readiness | `GET /v1/health` |

Navigation labels, in order: **Route map, Assess, Live, Samples, Reports, System**. Use these exact words.

---

## 5. The data layer comes first

The interface is only as honest as its types.

### 5.1 Contract handling

- Generate the client from the backend OpenAPI file with `openapi-typescript`. Pin to the published contract version and show that version in the System page.
- Until the contract exists, use typed fixtures in `web/src/mocks/`. Every fixture file starts with `// MOCK: replace with the published contract`. Mock mode shows a persistent, non-dismissible ivory banner: "Showing mock data. Values are not measurements."
- Record field, unit or status questions in `docs/frontend/CONTRACT_QUESTIONS.md`. Do not invent a permanent shape and do not edit backend files.
- Remove all mock values from the final demo build. A CI check fails the production build if the mock banner string or `src/mocks` is imported.

### 5.2 The value type that prevents fake zeros

Every scientific number in the UI passes through one discriminated union. Components never receive a bare `number | null`.

```ts
// Illustrative. The real shape comes from the published contract.
type Metric<TUnit extends string = string> =
  | { kind: 'measured'; value: number; unit: TUnit; validity: 'valid' | 'limited'; n?: number; lowerLimit?: number }
  | { kind: 'unknown'; reason: ReasonCode }          // null in the API: not measured
  | { kind: 'unsupported'; reason: ReasonCode }      // e.g. no calibration, below minimum resolution
  | { kind: 'uncalibrated'; pixelValue: number; unit: 'px' }; // never relabelled as mm
```

Rendering rules for `<MetricValue />`:

| Kind | Display |
|---|---|
| `measured`, value 0 | `0` with unit, in full ivory. This is a real zero. |
| `measured`, limited | value with a small "limited" chip and the reason in a tooltip |
| `unknown` | an em-dash glyph in `--text-3`, plus the reason text beneath ("No GPS fix") |
| `unsupported` | a hatched pill reading the reason ("Scale not calibrated") |
| `uncalibrated` | value in pixels with `px` unit and the label "pixels only" |

`0` and an em-dash must never look alike. A missing value must never render as an empty cell, a `0`, or a green state.

### 5.3 State machines

**Job lifecycle** (the only place a numbered or ordered stepper is justified, because it is a true sequence):
`received → validated → queued → processing → succeeded | partial | failed`

Show it as a horizontal stepper of five dots. Completed steps are filled ivory. The current step pulses once every 2 s (disabled under reduced motion). `partial` is drawn in `--review` colour with the text "Partial result" and lists what is missing. `failed` shows the typed reason code and a "Try again" action. **A finished upload alone never shows a success state.** Success is only `succeeded`.

**Source mode:** `still | live | replay`. Persistent chip on every sample card, sample detail header, segment row and report header. Replay is never styled like live. Live uses a teal dot; replay uses an ivory outlined chip with a rewind glyph; still uses a plain outline with an image glyph.

**Quality:** `accepted | limited | rejected` with reason codes (decode, surface domain, sharpness, glare, scale, plane stability, blur, resolution, feature completeness). Reasons render as plain sentences, not codes. Keep a lookup table `reasonCopy.ts`; unknown codes fall back to "Not supported yet: {code}".

**Condition:** `good | bad | review | unknown` plus an independent `severeDefectFlag`.

**Score status:** `calibrated` renders "Visual condition index". `provisional` renders "Provisional reference-deviation index" with an info tooltip. Never drop the word "provisional".

### 5.4 Data fetching

- TanStack Query. Job polling: 1 s while `received | validated | queued | processing`, with backoff to 3 s after 30 s, stop on terminal states. Pause polling when the tab is hidden.
- Live session: poll the session/segments endpoints at the interval the contract specifies. Show `lastCaptureAt` and `lastProcessedAt` from the response. **Do not construct capture times in the browser.** Upload time is not capture time.
- Stale result rule: if the backend flags a result stale, or `now - lastProcessedAt` exceeds the contract's staleness threshold, the card shows "Stale result" with the age, loses its teal accent and gets the unknown hatch. Never let an old result look current.
- Typed errors from the API map to three families, each with its own component: **validation** (fix your input), **analysis** (the job failed), **integration** (Google Maps, Bedrock, storage). Keep Google Maps key/billing errors visually and verbally separate from analysis failures.

---

## 6. Pages and components

### 6.1 Header

- Logo mark (a simple road-perspective glyph in ivory, 28 px) plus the wordmark "RoadSight" in Urbanist 500.
- Nav pills as in section 1.1.
- Right side: API readiness dot (teal = ready, review colour = degraded, coral = down) with a tooltip fed by `GET /v1/health`. Poll every 30 s. The dot has a text equivalent for screen readers.

### 6.2 Left column cards (Route map page)

**Source filter row.** Four pill tiles: `All`, `Live`, `Replay`, `Still`, each with a count. Single select. Selected tile uses `surface-3` with an ivory outline. Counts are real counts from the API.

**Quality tiles.** Three tiles: `Accepted`, `Limited`, `Rejected`, each with a `display-l` number. Accepted carries a check glyph (teal), Limited an eye glyph (review colour), Rejected a cross glyph (coral). Clicking a tile filters the Recent samples list.

**Condition along route.** A line chart in a `surface-1` card.
- X axis: route distance (m or km, from the API). Y axis: the index value, range from the policy if supplied.
- The line is ivory at 90%. **The line breaks wherever a bin has no accepted samples.** Never interpolate across a gap. Draw the gap as a faint dashed hatch band labelled "Not sampled" on hover.
- A dashed horizontal line appears only when the score policy supplies a threshold; label it with the policy's own name.
- Mark only noteworthy bins with dots: severe-defect bins (outlined coral diamond) and the selected bin (teal dot). Not every point.
- Hero number above the chart: the median index across sampled bins, with the status label beneath ("Provisional reference-deviation index"). If there are no accepted samples the number is an em-dash and the card says "No accepted samples yet. Upload an image or start a session."
- Show coverage under the chart: "Sampled 1.8 km of 3.2 km" and a thin bar. Coverage is the headline honesty number, give it as much weight as the index.
- Chart implementation: custom SVG with `visx` primitives. Must support keyboard focus per bin (arrow keys move between bins) and expose a data table alternative.

**Recent samples.** Two-column grid of cards, newest first, max 8 then "View all".
- Thumbnail of the original image (16:9, radius 16) with the overlay faintly visible.
- Top row: source-mode chip, quality chip.
- Title: capture time from the record (`HH:mm:ss`, local time with date on hover).
- Chips: `GPS ±4 m` or `No GPS`; `Calibrated` or `Uncalibrated`.
- Footer: condition chip and, if present, the severe-defect diamond.
- Arrow-up-right opens `/samples/:id`.
- Empty state: a muted illustration-free tile with "Nothing sampled yet" and a single action.

### 6.3 Map (Google Maps JavaScript API)

Use `@vis.gl/react-google-maps`. Load the key from `import.meta.env.VITE_GOOGLE_MAPS_API_KEY`. The key is restricted by referrer and API. No AWS or Bedrock credentials ever appear in `web/`.

**Base map.** Use a Map ID with cloud styling, or a JSON style as a fallback, to match the reference: desaturated dark terrain/satellite with land at `#0A1716`, water at `#031211`, labels in ivory at 60%, roads in ivory at 12%. Our route layers must stand out above the base roads, so keep base roads very quiet. Disable POI clutter, transit and the default Google controls. Provide our own control pill (zoom in, locate, zoom out) at bottom-left, glass style, 44 px targets.

**Layers** (all from backend data, none invented):

| Layer | Draw | Rule |
|---|---|---|
| Route polyline | 3 px ivory at 40% under the bins | Real GPS samples only |
| 50 m reporting bins | 6 px round-capped polylines coloured by condition | Only where the API supplies trustworthy geometry |
| Unsampled stretches | 2 px dashed ivory at 22%, no colour | Never coloured Good or Bad |
| Raw GPS points | 4 px dots, `--text-2` | Toggle, off by default |
| Accuracy circles | translucent ivory ring | Radius = reported accuracy; toggle |
| Severe-defect markers | outlined coral diamond, 14 px | Independent of bin colour |
| Selected bin | teal outer glow ring (static, not animated) | One at a time |

**Hard rules.**
- No interpolation of condition through gaps.
- No public benchmark image or sample is ever pinned to an Indian coordinate.
- No camera location is invented. No full-lane coverage claim from a narrow strip. Tooltip text says "Sampled strip", never "Road".
- If a session has no GPS, hide the map zone and show the linear distance report in its place with a card: "Map unavailable. This session has no GPS fix, so condition is shown by distance only."
- Simulated GPS is labelled with a persistent "Simulated route" chip on the map. Real GPS shows its accuracy.

**Map failure states** (integration family, distinct from analysis failures):
- Key missing or invalid: "Google Maps can't load. The API key is missing or rejected. Check the key and its referrer settings." Show the linear distance report as fallback.
- Billing or quota: "Google Maps is unavailable for this project. Check billing and quota in Google Cloud."
- Network: "Map tiles didn't load. Check your connection." with "Retry".
Each includes a "Copy diagnostic" button for the error code. Detect with the Maps `gm_authFailure` handler and loader error callbacks.

**Selected-bin glass card** (floats on the map, anchored to the bin, 280 px wide):
- Title: "Bin 12, 600 to 650 m".
- Hero: median index in `display-l`, status line beneath.
- Rows: accepted samples, strip area (m² with validity), lower-tail index, unknown coverage in percent, serious observed flags.
- Arrow-up-right opens the session page filtered to that bin.
- Close on `Escape`.

**Segment table** (bottom drawer): columns `Bin`, `Distance`, `Accepted samples`, `Strip area`, `Median`, `Lower tail`, `Flags`, `Coverage`. Sortable, row selection syncs with the map and chart. Cells use `<MetricValue />`. Row hover `surface-3`. Sticky header. Virtualise above 200 rows.

### 6.4 Assess page (`/assess`)

Purpose: take one still image from selection to a result.

Layout: two columns on desktop. Left: drop zone and requirements. Right: live job stepper and result preview.

1. **Drop zone.** Dashed `--line-strong` border, radius 24, 280 px tall. Accepts JPEG/PNG. Shows file name, native pixel size and size in MB after selection. Requirements list beneath in plain text: accepted formats, max size (from the contract), "Include GPS in the file or enter coordinates if you have them." Manual grade input is an optional section (see 6.9).
2. **Upload flow.** `POST /v1/uploads` returns a private key and short-lived URL. Upload straight to it with progress (bytes, not fake percentages). Then `POST /v1/uploads/{id}/finalize`. Then poll the job. Copy at each step names the real stage: "Uploading", "Checking the file", "Waiting to be analysed", "Analysing".
3. **Result.** On `succeeded`, show a result card (thumbnail, condition chip, index, the two or three top reasons) and a primary "Open evidence" button. On `partial` or `failed`, show the typed reason and the action that fixes it. On `rejected` quality, say why in plain language and what a better image looks like.

Primary button: ivory fill, ink text, 48 px high, radius 12. Secondary: outlined ivory 20%.

### 6.5 Live page (`/live`)

Purpose: run and monitor a live camera or replay session.

**Start panel.** Choose mode with a two-option segmented control: `Live camera` and `Replay recording`. Replay copy is explicit: "Replay uses a recorded file. It tests the pipeline, not the camera." Show camera profile and calibration ID returned by the session record. If the camera profile is uncalibrated, show an `Uncalibrated` chip and the line "Measurements will be in pixels only."

**Session monitor** (the live-state strip, always visible while a session is active):

| Item | Source |
|---|---|
| Connection state (connected, reconnecting, lost) | session/health data |
| Camera state | session record |
| Last capture time | record, not browser clock |
| Last processed time | record |
| Received, processed, rejected, dropped counts | record (four tiles with `display-l` numbers) |
| Stale-result indicator | per 5.4 |

Under it: the latest sample card and a small map or distance strip. **Replay sessions wear a permanent ivory "Replay" banner across the top of the monitor.** A live session shows a teal dot with a single slow pulse (once per 2.4 s, disabled under reduced motion). Buttons: "Finish session" (calls `/finish`, then shows aggregation progress) and "Stop and discard" only if the contract supports it.

**Finish.** After `/finish`, show the aggregation job stepper, then link to the session summary and report.

### 6.6 Sample detail and the evidence viewer (`/samples/:id`)

This is the most important screen. The inspector compares image, overlay and numbers before trusting a conclusion.

```text
+--------------------------------------------------------------------------------+
| < Samples   Sample 7f3a   [Live] [Accepted] [Calibrated]              Report v  |
+----------------------------------------------+---------------------------------+
| EVIDENCE VIEWER                              | 58.2  Provisional reference-     |
|  [Original][Road area][Aggregate][Distress]  |       deviation index            |
|  +----------------------------------------+  |  [Review]  ◇ Inspect              |
|  |                                        |  |  Reasons (plain sentences)       |
|  |      image with toggled overlays       |  |                                  |
|  |                                        |  | Measurements (tabs)              |
|  +----------------------------------------+  |  Surface | Distress | Geometry   |
|  Compare ◄──────●──────► (original/overlay)  |  Position | Versions              |
|  Legend with pattern + colour                |                                  |
+----------------------------------------------+---------------------------------+
```

**Viewer.**
- Image rendered from the returned source image at native resolution, with pan and zoom (wheel, pinch, keyboard `+ - 0` and arrows). Show native pixel dimensions and the current zoom.
- Layer toggles (checkbox chips, keyboard operable): original, road region of interest and rectification, observed area, eligible texture area, ignored area, distress area, aggregate instances, crack mask, pothole mask. Only offer layers that the response actually supplies. A layer that is unsupported appears disabled with its reason.
- Overlay rendering: each layer uses a colour **and** a pattern (solid, stripe, dots, outline) so no layer relies on colour alone. Default opacity 55%, with a slider.
- Compare slider to reveal original versus overlay.
- Legend lists every visible layer with its pattern swatch, the area it covers and the denominator used (observed area, eligible area). The legend always shows the scale source: "Calibrated, 0.91 mm per pixel" or "Pixels only".
- If the sample is rejected, show the image with a banner stating the first rejection reason and hide measurement panels.

**Score panel.** Hero number (`display-xl`) with dimmed decimals, status label directly beneath, condition chip, severe-defect diamond (separate from the number) with the text "Inspect" and why. Show model, reference and score policy versions in a "Versions" tab. The score is an em-dash with a reason when null. Confidence is shown as supported components with descriptive states (for example "Image quality: good", "Scale: calibrated", "Reference support: supported"), not as a percentage, unless the contract says it is a calibrated probability.

**Measurements tabs.**

| Tab | Contents (only returned fields) |
|---|---|
| Surface | Visible chip count, density (per area, with eligible area and minimum visible size), 2D equivalent diameter distribution, aggregate union coverage, adjacent-boundary gap median, IQR and p90 with valid count and measurement lower limit, texture proxies |
| Distress | Crack skeleton length, crack and pothole mask area and extent, repair/patch flag, ravelling/bleeding/polishing as human-review flags |
| Geometry | Scale source and value, geometry validity, plane stability, observed area, uncertainty |
| Position | GPS coordinates, accuracy, source, route distance, simulated or real, capture and receive times |
| Inclination | Grade percent and degrees, source, time, uncertainty, validity. If unsupported, show "No verified grade for this sample" and the source requirement. Never compute grade in the browser from pitch, map elevation or route shape. |
| Versions | model, reference, feature and score versions; estimator versions per metric |

Labels use plain language. Use "visible chips (2D exposed appearance)" and "texture proxy". **Never** write sieve gradation, binder thickness, pavement depth, certified roughness or structural condition. Reference comparisons show the known-good value and the direction of difference ("higher than reference", "lower than reference"), not a verdict.

Distribution charts use small SVG histograms with the minimum measurable size marked as a vertical dashed line; bars below it are hatched and labelled "Below the size the camera can measure".

### 6.7 Session summary (`/sessions/:id`)

Hero: coverage ("Sampled 1.8 km of 3.2 km"), accepted sample count, median index with status, serious-flag count. Below: the same condition-along-route chart and segment table at full width, then a list of unknown or unsampled stretches ("0.6 km between 1.2 and 1.8 km was not sampled"). The unknown stretch list is not optional.

### 6.8 Report page (`/reports/:id`)

- Header: title, session, date, source mode chip, report version.
- **Structured findings first**, as a table rendered from the stored facts. Numbers come from structured data only.
- **Narrative second.** A card with a status badge:
  - "Generated by Bedrock" with the model ID from the response, or
  - "Template summary" when the backend reports a deterministic fallback, with the line "The language model was unavailable, so this summary was built from a template."
- Evidence references in the narrative render as chips that scroll to and highlight the cited sample or bin. If a reference cannot be resolved, show it as an inline "Unverified reference" chip. Never parse the narrative text to compute or fill any value.
- **Limitations** and **Recommended inspection actions** are always visible sections, never collapsed. If the response omits them, render "The report did not include limitations" in review colour. This is an error state.
- "Export report" opens the link the backend supplies. Do not generate PDFs in the browser.
- Print stylesheet: ivory background, ink text, no map, no glass.

### 6.9 Optional manual or sensor grade input

Only if the contract exposes it. A small form in the Assess and Live pages: grade value (percent), source (manual, sensor), measurement time, uncertainty, zero-check done (yes/no). Send through the schema and display it exactly as returned. Label: "Verified grade input". The UI does not validate physics, it only enforces required fields.

### 6.10 System page (`/system`)

Table of readiness rows from `GET /v1/health`: model, worker, storage, Bedrock, Google Maps readiness, queue depth, contract version. Each row: status dot, plain description, last checked time. Google Maps readiness sits in its own labelled group, "Browser integration", separate from "Backend services". Show the OpenAPI contract version the client was built against and flag a mismatch with the server's version in review colour.

---

## 7. Component inventory

Build these as small, typed, testable units under `web/src/components/`. Everything is keyboard accessible and themed from the tokens above.

| Component | Notes |
|---|---|
| `AppShell`, `Header`, `NavPill` | Section 3 and 6.1 |
| `Card`, `GlassCard`, `Tile` | Radii and surfaces from 2.4 |
| `MetricValue`, `HeroNumber` | Section 5.2 and 1.1 (dimmed decimals) |
| `ConditionChip`, `QualityChip`, `SourceModeChip`, `ScaleChip`, `GpsChip` | Outlined chips with glyphs |
| `SevereDefectFlag` | Outlined diamond plus "Inspect" |
| `JobStepper` | Section 5.3 |
| `LiveMonitor`, `StaleBadge` | Section 6.5 and 5.4 |
| `RouteChart` | Gapped line chart, keyboard navigable, with data table fallback |
| `SampleCard`, `SampleGrid` | Section 6.2 |
| `RouteMap`, `BinLayer`, `GapLayer`, `GpsLayer`, `MapControls`, `SelectedBinCard`, `MapErrorPanel` | Section 6.3 |
| `SegmentTable` | Virtualised, sortable |
| `EvidenceViewer`, `LayerToggleList`, `CompareSlider`, `Legend` | Section 6.6 |
| `MeasurementTabs`, `Histogram` | Section 6.6 |
| `ReportView`, `NarrativeCard`, `ReferenceChip`, `LimitationsList` | Section 6.8 |
| `UploadDropzone`, `ProgressBar` | Section 6.4 |
| `EmptyState`, `ErrorPanel` (validation, analysis, integration variants) | Section 8 |
| `HealthTable` | Section 6.10 |
| `MockBanner` | Section 5.1 |

---

## 8. Copy and states

Write for an inspector, in plain language. Sentence case. Active voice. Name things by what they are, not by how the system is built. An action keeps one name through the flow ("Analyse image" becomes "Analysed", not "Done"). Errors say what happened and what to do, and do not apologise.

| Situation | Copy |
|---|---|
| No samples | "Nothing sampled yet. Upload an image or start a session." |
| No GPS | "Map unavailable. This session has no GPS fix, so condition is shown by distance only." |
| Unsampled stretch | "Not sampled. We have no measurements for this stretch." |
| Uncalibrated | "Pixels only. Without calibration, sizes can't be given in millimetres." |
| Rejected: blur | "Rejected. The image is too blurred to measure. Try a slower pass or a faster shutter." |
| Rejected: surface | "Rejected. This image doesn't show a supported road surface." |
| Provisional score | "Provisional reference-deviation index. It compares this surface to a known-good reference and is not yet calibrated to human ratings." |
| Review | "Needs review. Evidence is mixed. Compare the image and overlay before deciding." |
| Stale | "Stale result. Last processed 14 s ago." |
| Replay | "Replay. This is a recorded file, not a live camera." |
| Upload done, analysis pending | "Uploaded. Analysis hasn't finished yet." |
| Analysis failed | "Analysis failed: {plain reason}. Try again or choose a different image." |
| Bedrock fallback | "The language model was unavailable, so this summary was built from a template." |
| Maps key problem | "Google Maps can't load. The API key is missing or rejected." |

Loading uses skeletons that match the final layout (no centred spinners). Skeletons use `surface-2` with a single slow shimmer that stops under reduced motion. Every error panel has a retry or a next action.

---

## 9. Motion

Spend motion in one place and keep the rest still.

**The one orchestrated moment.** When the Route map page first loads with data: the map fits its bounds, then the route polyline draws on from start to end over 900 ms (stroke-dashoffset, `cubic-bezier(0.22, 1, 0.36, 1)`), bins fill in behind it in order, and the left-column cards fade in with a single 160 ms group fade. It plays once per page load, never again on data refresh.

**Motion that answers an action** is welcome: opening a card, selecting a bin (ring appears, card slides 8 px), toggling an overlay (opacity transition 160 ms), expanding the drawer (240 ms).

**Not allowed:** scroll-triggered entrances, per-card hover lifts, staggered dominoes, parallax, isometric tilt, 3D transforms, animated gradients, continuous box-shadow or filter animation. This is a measurement tool. Floaty effects undermine trust.

Rules: durations 120 to 300 ms for interaction, nothing under 120 ms. Only `transform` and `opacity` animate. All motion disabled when `prefers-reduced-motion: reduce`, replaced by instant state changes. The live pulse and stepper pulse are the only looping animations.

GSAP is not required. CSS transitions and the Web Animations API are enough. If a library is needed for the route draw, keep it to that one use.

---

## 10. Accessibility and quality floor

- WCAG 2.2 AA. Text contrast at least 4.5:1 (`--text-3` is the lowest allowed text colour; do not go dimmer for anything meaningful).
- Visible focus on every control: 2 px ivory ring with 2 px ink offset.
- Every condition and layer distinguishable without colour (glyph, pattern, text).
- Map is not the only way to read data: the segment table and chart data table carry the same facts. Map markers are reachable by keyboard through the table.
- Charts: keyboard navigation, `aria-label` summaries ("Condition along 3.2 km, sampled 1.8 km"), data table toggle.
- Live regions: job state changes and stale warnings announce through `aria-live="polite"`. Errors use `role="alert"`.
- Touch targets at least 44 px on touch devices.
- Overlay images have text alternatives describing the layer and what it covers.
- Language attribute set, document titles per route, skip link to main content.
- Responsive from 360 px wide. No horizontal page scroll. Tables and long content scroll inside their own container.
- Performance: route-level code splitting, the map library lazy-loaded on routes that use it, images served at needed size, Largest Contentful Paint under 2.5 s on a mid-range laptop, no layout shift from font swap (use `size-adjust` fallbacks).

---

## 11. Tech and structure

- React 18, TypeScript (strict), Vite, React Router, TanStack Query.
- Styling: Tailwind CSS with the tokens in 2 mapped into the theme, plus a small CSS file for glass, hatch patterns and map overlays.
- Maps: `@vis.gl/react-google-maps`.
- Charts: `visx` primitives, custom SVG.
- Client: `openapi-typescript` plus a thin `fetch` wrapper that returns typed `Result` objects, never throws raw errors into components.
- State: server state in TanStack Query, local UI state in component state, one tiny store (Zustand) only for the selected session, bin and layer toggles.
- Tests: Vitest and Testing Library for units, Playwright with `@axe-core/playwright` for flows and accessibility, run against the fixtures.
- Lint: ESLint, Prettier, `tsc --noEmit` in CI.
- Secrets: only `VITE_GOOGLE_MAPS_API_KEY` and the API base URL reach the browser. `.env*` files are git-ignored.

```text
web/
  index.html
  vite.config.ts
  src/
    main.tsx
    app/            routes, providers, shell
    api/            generated client, query hooks, error mapping
    contract/       pinned OpenAPI types, version constant
    mocks/          typed fixtures (MOCK only)
    lib/            metric.ts, reasonCopy.ts, format.ts, polling.ts
    components/     (section 7)
    features/
      route-map/  assess/  live/  sample/  session/  report/  system/
    styles/         tokens.css, glass.css, patterns.css
    test/
```

---

## 12. Required tests (the honesty cases)

Write these first. They matter more than visual tests.

1. A measured `0` renders as `0` with its unit. `unknown` renders as an em-dash with a reason. They are never visually identical.
2. A `null` score never renders a coloured condition and never renders as 0.
3. Uncalibrated metrics render in `px` and never in mm or cm².
4. Live, replay and still show different chips on every surface where a sample appears. A replay never shows a teal live dot.
5. A session without GPS shows the "Map unavailable" state and the linear distance report, and loads no map tiles.
6. A `partial` job and a `failed` job each show their reasons and never show a success state. An upload that finished while the job is `queued` is not shown as succeeded.
7. A stale live result gets the stale treatment and age.
8. An unsampled bin is never coloured Good or Bad on the map, and the route chart line breaks at it.
9. Google Maps key, billing and network errors render the integration error panel, not the analysis error panel.
10. A Bedrock narrative with a fallback flag shows the template badge. An unresolvable evidence reference shows "Unverified reference". No number in the report is parsed from narrative text.
11. The inclination tab shows nothing derived when the field is unsupported.
12. All condition states pass a greyscale distinguishability check.
13. Production build fails if mock data or the mock banner is included.

---

## 13. Self-critique checklist for the build

Run this against rendered screenshots, not the code, at 1440 px and 390 px.

**Does it match the bar?**
- Is it recognisably a two-zone dark dashboard with pill navigation and a full-bleed map?
- Are hero numbers thin and large, with dimmed decimals and units?
- Is teal used for signal only, with at most two teal elements per card?
- Are there no drop shadows and no gradient washes?
- Do nested radii step down correctly?

**Is it honest?**
- Can you tell at a glance what is measured, what is unknown and what is unsampled?
- Does coverage have as much visual weight as the index?
- Is every score labelled provisional or calibrated?
- Is replay impossible to mistake for live?

**Is it free of template tells?**
- No all-caps eyebrow labels, no numbered markers on non-sequences, no middle-dot meta strings, no spaced-em-dash labels, no arrows appended to button text, no monospace labels, no identical grid of cards with the same weight.
- No fabricated KPI, no stock illustration, no fleet vocabulary left over from the reference.

**Does it hold up?**
- Remove one accessory: what single element can be cut without losing meaning? Cut it.
- Keyboard-only walk-through of Assess, Live, Sample detail and Report.
- Reduced-motion and greyscale passes.

---

## 14. Handoff notes to other roles (write these in `docs/frontend/`)

Create `docs/frontend/CONTRACT_QUESTIONS.md` and open it with these questions. They are blockers or likely blockers.

**For backend**
1. Does each segment carry geometry (polyline or coordinates) per bin, and a flag for unsampled stretches, or should the UI derive gaps from distances?
2. What are the staleness threshold and the polling interval for live sessions?
3. Which report fields are guaranteed (limitations, inspection actions, evidence references, fallback flag, model ID)?
4. How are evidence images and overlay layers returned (signed URLs, per-layer masks, one composite)? What is their expiry?
5. What are the max upload size and accepted formats?
6. Is "Stop and discard" a supported session action?
7. Is there a documented reason-code list for the copy table in section 8?

**For ML**
1. Mask legend: class names, one definition per layer, and the denominator for each area.
2. Minimum measurable chip size and gap width per camera profile.
3. Score policy fields: threshold names, whether SQI is calibrated or provisional, and the review band definition.
4. Which confidence components exist and their allowed descriptive states.
5. Which human-review flags (ravelling, bleeding, polishing) will be returned and how.

**For the client**
1. Approve the two extra condition hues (coral for Bad, amber for Review) or supply alternatives within the palette.
2. Confirm the font pair or supply brand fonts.
3. Confirm the logo mark or supply one.
4. Confirm whether the judge requires moving live capture, since that changes how prominent the Live page is in the demo.

---

## 15. Demonstration order the UI must support

Follow final plan Sections 13 and 17 for the release gates. The interface must make this sequence smooth:

1. Open Route map with real session data, point at coverage and the gapped chart.
2. Assess a real still image: upload, stepper, result.
3. Open the evidence viewer, toggle overlays, compare image and numbers.
4. Show an actual connected live camera session, then the clearly labelled replay backup.
5. Show the report: structured facts, Bedrock narrative badge, limitations, inspection actions.
6. Show the System page proving readiness.

If camera access, calibrated chip detail, physical grade or Indian transfer is unproven, the UI says so on the relevant screen. A feature that cannot be proven is shown as unsupported, never as complete.
