# RoadSight AI — Final Implementation Plan

**Version:** 1.0 · **Prepared:** 15 October 2026 · **Target:** Indian roads, initially one local asphalt-road operating domain.

**Status:** Decision-ready engineering plan, not a claim of completed implementation or validated accuracy. Dataset metadata has been checked against primary sources where identified below; dataset archives, individual masks, and model performance have not been audited or tested in this planning session.

## 1. Decisions that govern this plan

The current user's decisions supersede instructions and assumptions embedded in the six supplied documents:

| Item | Final planning decision |
|---|---|
| Team and timeline | Three people; no stated deadline. Work by acceptance gates, not an invented sprint deadline. |
| Training compute | Google Colab. A local NVIDIA GPU is **not** assumed, despite the older handoff. |
| Required integrations | AWS, Amazon Bedrock, and Google Maps. AgentCore is not required and is excluded from the initial architecture. |
| Training data | Public datasets plus team-created annotations on public images. Local training-image collection is currently infeasible. |
| Human effort | Manual annotation and review are possible. Use this where it improves truth, not merely where automation fails. |
| Demonstration | Actual live road-camera capture is required. Replay is backup only. No live camera is currently available; obtaining access is a first-stage dependency. |
| Geography | India first. Foreign data may support pretraining and measurement-method development, but cannot establish Indian-road performance. |
| Scope discipline | Deliver the stated requirements before advanced edge cases. No dedicated speed-breaker/hump model in the first release. |
| Working name | RoadSight AI. Ghost-Rider is an earlier name for the same project. |

**Core recommendation:** Build a calibrated visible-surface assessment engine, train a small model with human-reviewed labels, compare appropriate surfaces with known-good references, and deploy an inspector-facing AWS application with Google Maps and Bedrock explanations. Start with public data, but acquire a real camera early and validate the frozen system on Indian live footage before claiming that the implementation works locally.

**The critical feasibility boundary:** No dataset verified here supplies the complete combination of Indian in-situ asphalt imagery, reliable physical scale, chip-instance labels, gap measurements, and independent condition ground truth. This is a missing dependency, not something a more complicated neural network fixes. The plan closes it through public-data annotation, acquisition of existing calibrated imagery where available, and a small live-camera acceptance exercise. If that final exercise is impossible, the live/local requirement remains unmet.

Local training collection and live acceptance testing are different activities. The former is not a prerequisite in this plan. The latter is necessary to substantiate the required live Indian-road demonstration. Do not quietly turn test footage into training data and still call it unseen.

## 2. Requirements, boundaries, and completion criteria

The supplied Honeywell image is the directly available formal brief. The chip-specific clarification is quoted in the previous conversations; retain it as a working requirement, while confirming its precise interpretation with the judges. An ambiguous older verbal exemption does not remove inclination from the formal brief.

| Requirement | Implementation | Evidence required before calling it complete |
|---|---|---|
| Capture and preprocess representative road images | New-image upload plus actual camera adapter; quality gate and preserved originals | A new image and live frame traverse the same engine |
| Identify visible aggregate; count per m² | Reviewed aggregate-instance labels; segmentation and area-normalized counting | Human count comparison, denominator and scale provenance |
| Chip boundary width | Visible inter-aggregate spacing plus chip equivalent diameter, with explicit definitions | Endpoint/mask agreement and resolution limits; judge confirms interpretation |
| Roughness | Image-derived texture proxy | Repeatability and association with human visual assessment; not physical depth |
| Defect size, density, distribution | Crack/pothole masks; projected area, crack length, spatial distribution | Held-out mask metrics and size error where scale exists |
| Known-good learning and unknown-image assessment | Reference model fitted to reviewed good patches; calibrated score | Disjoint development and test groups; condition-rating agreement |
| Inclination | Separate grade estimate with stated source and assumptions; supporting measured sensor input allowed | Reference comparison or an explicit judge exemption |
| Continuous route assessment | Continuous acquisition, selective processing, distance aggregation, coverage accounting | Actual live route/strip data; gaps and latency visible |
| Good/Bad and quality score | Custom Surface Quality Index, binary output plus review/unknown state | Frozen policy, validation confusion matrix, rejection rate |
| Dashboard, report, findings, recommendations | AWS web app, Google Maps, structured report, Bedrock narration | Inspectable evidence, real integration calls, failure recovery |
| Lighting, speed, surface variation | Bounded operating envelope and separate stress evaluations | Results by condition, including rejected frames |

**Initial supported domain:** one reviewed asphalt surface family, dry daylight, close-range downward/slightly forward imagery, low-speed controlled inspection, one camera profile. Concrete, gravel, water-covered pavement, unreadable images, and unsupported cameras return a limited result or review request. This is a local prototype scope, not a nationwide generalization claim.

**Do not claim:** structural strength, load capacity, internal aggregate gradation, binder-film thickness, water permeability, friction, pothole depth/volume, IRI, certified PCI, or physical MTD/MPD from ordinary RGB appearance. Surface texture and physical roughness are different measurements; the [FHWA texture advisory](https://www.fhwa.dot.gov/pavement/t504036.cfm) provides the engineering background.

An upload without scale may still yield observed distress or image features. It cannot yield trustworthy mm, cm², or count/m². A measured zero and an unavailable value must remain distinct.

## 3. What survives from each supplied plan

| Supplied document | Keep | Change or reject |
|---|---|---|
| `Claude-Road quality analysis system design-20261015-2115.md` | Texture-centered interpretation, calibration, known-good reference, human counting, deterministic narrative inputs | Do not use generic phone tilt as road slope; a sample every 50 m is not continuous inspection; small good-only training does not automatically make a reliable condition score |
| `02_road_quality_master_plan.md` | Pipeline separation, units, reference learning, quality gates, fallbacks, validation axes | Replace its mandatory self-capture assumption; remove automatic YOLO-seg training from RDD boxes; remove fixed unvalidated score bands and inclination penalties |
| `master_context_architecture_document.md` | FastAPI, storage/API contracts, route metadata, physical area reasoning | Reject windshield-first chip analysis, box-to-area inference, arbitrary 10 m certainty, pitch-as-slope, raw weighted area score, and unsupported repair prescriptions |
| `RoadSight_AI_HackHive_Honeywell_Master_Project_Handoff.md` | Strongest measurement definitions, visibility gates, instance-label policy, unknown handling, single-engine design, held-out evaluation | Cloud is now mandatory; Colab is the confirmed compute; local training capture is unavailable; live access must be obtained; defects/route/inclination cannot disappear from formal scope |
| `road_surface_quality_research.md` | Useful dataset leads and recognition of the chip-label gap | Several dataset identities, counts, label types, scale claims, and licensing assumptions are wrong or unsupported; use the corrected registry below |
| `3ultraanalaysis.md` | Better provenance discussion, split risks, source inventory, some genuine calibrated-image leads | Reject unpaired laser→RGB validation, “zero leakage guaranteed,” size-class labels as calibration, unsupervised masks as truth, and categorical claims that relevant Indian data do not exist |

### Important contradiction resolutions

1. **One camera, several software outputs.** A low, stable, close-range camera is the preferred live setup because chips require detail. Upload and live mode share an engine. Do not build a second mandatory dashcam system.
2. **Capture interval is not reporting interval.** Acquire continuously; process frames based on usable coverage. Begin with 50 m reporting bins, configurable. Never interpret one small patch as a census of a bin.
3. **Scale does not create labels.** A 1 mm/pixel image still needs human-visible particle boundaries. Crack labels cannot train aggregate segmentation merely by adding a head.
4. **Scale does not create optical resolution.** Upscaling, super-resolution, deblurring, SAM, and depth models cannot supply missing measurement evidence.
5. **Good-only learning measures familiarity.** It becomes a condition index only after comparison with independently assessed non-good examples.
6. **Sparse data do not justify many models.** Implement one classical baseline and one small learned challenger per necessary task. Stop model proliferation when data quality is the limiting factor.
7. **Slope is context, not automatic damage.** A sound sloped road is not intrinsically bad. Report grade separately and include any grade-related flag only when justified by a defined inspection rule.
8. **Locality is an evaluation requirement.** Indian images are not interchangeable with all Indian roads, and foreign benchmark success is not Indian validation.

## 4. Corrected dataset selection

### 4.1 Evidence levels

- **Metadata checked:** primary paper/repository/catalogue read in this review.
- **Access pending:** full archive or permission not obtained here.
- **Content pending:** decoding, masks, duplicates, scale propagation, and label quality still need inspection.
- **Selected conditionally:** useful role identified, but admission gates must pass before training.

No dataset below is called clean, leakage-free, or training-ready merely because its page opens. The recommendations are role-specific; a single universal “fit score” would hide the difference between chips, distress, scene quality, and GPS replay.

### 4.2 Selected sources and their exact roles

| Source | Verified facts / useful property | Selected role | Limits and admission conditions |
|---|---|---|---|
| **RDD2022 — India subset** | The full release has 47,420 images across six countries, including India. Main challenge damage categories are longitudinal, transverse, alligator cracks and potholes. [Paper](https://arxiv.org/abs/2209.08538), [official repository](https://github.com/sekilab/RoadDamageDetector) | **Primary Indian distress source.** Use official Indian images; manually add masks to a carefully selected subset if precise segmentation is needed | Bounding boxes are not pixel masks. No chip or metric-scale truth. Audit actual class IDs and splits; do not combine RDD2020/2022 or mirrors without ancestry deduplication. Freeze an Indian test subset before annotation-driven training |
| **ISTD-PDS7** | 18,527 images; original CCD imagery documented at 0.91 mm/pixel; distress and negative samples, not aggregate labels. Access is described as by request. [Primary paper](https://www.mdpi.com/2072-4292/15/7/1750) | **First public-data candidate for scaled aggregate feasibility**, and optional distress pretraining | Inspect original scale-preserving files and asphalt subset; obtain chip annotations from humans. A published original GSD must be propagated through crops/resizing. Fine gaps may remain unresolved. Data-use terms and parent IDs must be confirmed |
| **DeepCrack CRKWH100** | 100 visible-light line-camera pavement images at stated 1 mm GSD. CrackLS315 uses laser illumination; Stone331 is cut-stone crack imagery. [Author repository](https://github.com/qinnzou/DeepCrack) | **Access fallback and independent chip-visibility pilot**; cross-source crack evaluation where compatible | Small, non-Indian and not guaranteed RGB or chip-resolving. No aggregate labels. Keep laser and cut-stone data out of the primary appearance reference. Academic-use statement needs appropriate reuse confirmation |
| **GAPs original images / GAPs 10m** | Original imagery has documented 1.2 mm/pixel; the 10m release has 20 large expert-labeled images. Academic access requires a form. [University source](https://www.tu-ilmenau.de/universitaet/fakultaeten/fakultaet-informatik-und-automatisierung/profil/institute-und-fachgebiete/institut-fuer-technische-informatik-und-ingenieurinformatik/fachgebiet-neuroinformatik-und-kognitive-robotik/data-sets-code/german-asphalt-pavement-distress-dataset-gaps) | **Backup scaled imagery and reference-method validation** | Very few independent scenes in 10m data. Confirm both physical axes for that version; do not infer isotropic scale from a nominal road length. Do not count crops as independent roads |
| **Pavementscapes** | 4,000 top-down grayscale images, six damage categories; selected images contain damage. [Paper](https://arxiv.org/pdf/2208.00775), [repository](https://github.com/tongzheng1992/Pavementscapes) | **Preferred optional distress-mask pretraining source**, followed by Indian fine-tuning | Not a ready good-road reference. Claimed 1–2 mm GSD not established by this review. License/access and mask codebook must pass audit. Do not export cm measurements from it without verified scale |
| **Indian seasonal paved/unpaved road dataset** | Nashik/Mumbai imagery; 4,242 originals plus rotated versions, and video. [Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8933537/), [dataset](https://data.mendeley.com/datasets/tj2m7zz4rg/2) | **Indian robustness/challenge set**, especially wet appearance and unsupported surfaces; optional replay backup | Start from originals; group rotations, resized copies and video siblings. No assumed metric scale, chip labels, GPS track, or certified condition score. Inspect raw images before accepting texture relevance |
| **StreetSurfaceVis — new optional suggestion** | 9,122 German street-level images with surface/quality labels and coordinates; suggested test cities are held out. [Author dataset](https://zenodo.org/records/11449977) | **Optional external scene-quality/map integration check**, not an Indian training requirement | Different viewpoint and task from chip analysis. Preserve image attribution/Mapillary terms. Do not transfer scene grades onto arbitrary close-up patches or place German images on Indian roads |
| **Small permitted comma2k19 excerpt** | Video plus phone-class sensors and pose metadata. [Author repository](https://github.com/commaai/comma2k19) | **Optional synchronization/replay test only**, if needed | Not local performance evidence, not chip-scale road imagery, not ground-truth road grade. Confirm data terms rather than assuming repository code license covers every asset. No full 100 GB download needed |

**Acquisition order:** obtain a small official Indian distress sample and the scale-documented candidate sample first; request gated calibrated datasets concurrently through the team. Do not download every dataset. Move to the next source when access, rights, scale, or visibility prevents progress. The team sends requests; no external messages were sent during this review.

**Operational training choice:** manually reviewed public aggregate patches form the chip dataset. Public Indian distress images form the local damage dataset. These are separate datasets, with separate masks, references, and evaluations. Foreign aggregate data are an explicitly provisional bridge until Indian camera tests demonstrate transfer.

### 4.3 Other proposed datasets: disposition

| Candidate or family from the research packets | Decision and reason |
|---|---|
| Mendeley `w86hvkrzc5/2` / later RSCD variants | **Do not use as Good/Bad truth.** The checked release has 27 surface-state categories covering friction-level/material/unevenness concepts, not the alleged PSCI grades. Optional surface-domain experiment only. [Source](https://data.mendeley.com/datasets/w86hvkrzc5/2) |
| `RaymondAllen/asphalt-3d-laser-texture` | **Defer.** Primary HF card was inaccessible during this review. Even if every reported height/PTV detail is correct, unpaired height maps cannot supervise or validate RGB→MTD/PTV on different surfaces. PTV is not itself MTD/MPD |
| `KeenForgeAI/RoadCrack_DL_HY-corrected` | **Reserve, not primary.** Card inaccessible here; supplied report describes boxes and duplicate cleanup. Prefer India-first data. Hash-based cleanup cannot guarantee site independence, and discarded empty annotations may have removed valuable negatives |
| Giordani/Arcioni road damage dataset | **Optional detector check only.** Primary paper reports 2,009 images, boxes/four-vertex labels, not the claimed 2,099 precise masks. Setup descriptions are not per-image calibrated geometry. [Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181123/) |
| RoadDefects-ISeg | **Small backup mask source after audit.** Mixed upstream sources; reannotation claimed; four classes include lane and speed breaker. Do not infer Indian capture from Indian author affiliation. Resolve academic-use wording alongside CC BY claim; deduplicate ancestors. [Record](https://zenodo.org/records/17194814) |
| UAV-PDD2023 | **Defer.** UAV detection domain, not chip measurement; extra training source only if it fixes a measured failure. [Record](https://zenodo.org/records/8429208) |
| CRACK500, CFD, CrackTree, AEL, DeepCrack variants, Crack-Seg | **Choose at most one crack-mask backup.** Trace original ancestry and licenses; distinguish centerline labels from actual-width masks. Do not combine versions blindly or use width-inaccurate labels for metrology |
| SDNET2018 | **Not needed.** Concrete classification is an indirect detour; generic pretrained encoder is a simpler starting point |
| Roboflow loose-aggregate/8mm/20mm/40mm projects, Hannover visual granulometry | **Not primary.** Loose particles differ from embedded pavement. A physical size in a class name does not establish image scale. Optional annotation-method practice only; [Hannover source](https://data.uni-hannover.de/dataset/visual-granulometry) |
| Asphalt AC16 specimen images | **Method experiment only.** Laboratory specimens are not automatically in-service surfaces. No good/bad or in-situ scale assumptions. [Record](https://zenodo.org/records/10964320) |
| Roboflow severity/ravelling projects, PaveDistress, HiRPD, BPC, UWGB-StreetCrack, 3DCrack | **Unadmitted leads.** Require original release, actual files, label semantics, provenance and rights. Not reasons to postpone the chosen baseline |
| StructDamage, PaveSync, LRDD/OpenCrack-style aggregations | **Catalogue/reference only initially.** Merged datasets can import the same source into both train and test; original-source lineage is mandatory |
| deep_pavements_surface_patches, other HF/Kaggle quality/classification sets | **Optional weak-label leads.** No assumption that disease classes equal condition grades or that missing distress labels mean good pavement |
| BDD100K, KITTI, Mapillary Vistas/other sequences | **Reserve for a specific missing function.** Driving-scene data are not chip labels. Avoid a large foreign replay pipeline when an Indian live feed is required |
| Deeksha9 / empty or undocumented HF sets | **Quarantine, not “proven corrupt.”** Viewer decoding failure can be a packaging failure; inspect bytes before declaring image corruption. They are not worth admitting now |
| MVTec AD, DTD, general texture assets, synthetic Voronoi stones | **Algorithm tests only.** Synthetic shapes help unit tests; generated texture is not road-condition truth |
| Recent unverified paper/model claims in the appendices | **Background only.** No architecture is selected because an abstract reports a high metric on a different dataset |

### 4.4 Corrections that materially change implementation

- The research packets confused ISTD-PDS7 with a different 315-image crack dataset. Their proposed aggregate labels do not exist merely because scale is documented.
- RDD2022 is not the approximately 26k-image 2020 release, and its country list includes Norway, not the report's Brazil substitution.
- Pavementscapes is Chinese inspection imagery; it is not a generic US/European good-road texture set.
- A failed dataset viewer is not proof of damaged image files. An official split is not proof of no leakage. “Verified download” in a previous report is not a completed byte-level audit here.
- Published camera height, a guessed lane width, a typical manhole diameter, image DPI, or a nominal coin denomination cannot substitute for verified per-image geometry.
- The blanket statement that images from 1–2 m make chips subpixel is false: footprint, pixel count, optics, angle and exposure determine resolution. Conversely, 5–10 cm working distance is not automatically useful or in focus.
- A printed checkerboard must be physically measured; printing does not guarantee an asserted dimensional tolerance.
- “No public chip dataset was verified in this review” is defensible. “No such dataset exists anywhere” is not.

## 5. Gate 0 — prove data and camera access before committing

Run these two tracks immediately. Neither depends on a trained neural network.

### 5.1 Public-data feasibility track

1. Obtain approximately 20–30 native-resolution samples from the preferred scale-documented source, spanning intact-looking and visibly distressed asphalt. Keep original files and documentation.
2. Two people independently inspect randomly chosen patches at native resolution. Can they consistently distinguish separate exposed chips? Can they locate adjacent boundaries? Does zooming only magnify ambiguity?
3. Verify GSD separately in x/y, image resizing history, distortion assumptions, and whether the delivered version matches the paper. Ask the source owner for missing original metadata if necessary.
4. Annotate 10 small patches twice, without model suggestions initially. Compare counts, masks, and chosen gap endpoints. Establish the human disagreement floor.
5. Run a classical segmentation pilot. Compare model error with human disagreement. Inspect split/merge errors, not just total count, since opposing errors can cancel.
6. Select a resolvable size range. At roughly 1 mm/pixel, a 1 mm gap is about one pixel and is not a trustworthy width measurement. If only coarse gaps are measurable, state the lower reporting limit and resolve whether that satisfies the judge.
7. Stop and seek better existing images if humans cannot label the required detail. Do not create pseudo-ground-truth from watershed or SAM and claim the requirement solved.

**Gate output:** `DATA_ADMISSION.md`, sample contact sheet, original-source manifests, small reviewed annotation set, supported feature-size range, and an explicit go/no-go for chips and gaps separately.

### 5.2 Camera acquisition track

Assign one teammate to secure access through the college robotics/CV/civil engineering lab, a faculty project, a teammate's controllable phone, or a short-term loan/rental. Ask for one camera, computer connectivity, a rigid mount, a measured target, and a safe test location. This is a procurement/access plan; no purchase or outreach is performed by this document.

**Preference order:** borrowed device that passes the optical/live-stream test → borrowed UVC camera with suitable lens/control → action camera with workable live output and locked settings → global-shutter hardware only if measured motion distortion requires it. Do not buy a named model before testing a sample feed.

Acceptance checks:

- Native frame dimensions, focus, working distance, useful field of view, exposure control, actual live output and connection stability.
- A measured board captured at the intended road distance; held-out distances at center and corners.
- Whether autofocus, stabilization, digital zoom, or crop changes geometry.
- Live frames reach the server; a pre-recorded file is not accepted as this test.
- Safe low-mounted downward view on a permitted platform. Start stationary, then controlled slow motion. The prior under-number-plate idea is a candidate mounting arrangement, not proof of hardware access or safe clearance.

If a moving vehicle is explicitly required, a trolley/handheld live demo does not meet that requirement. It may be a bench milestone only. Confirm the organizer's minimum acceptable speed and whether low-speed moving capture qualifies.

**No camera access means live functionality is blocked.** Continue public-data software work, but do not label the final deliverable complete. Replay cannot remove this dependency.

### 5.3 Indian-domain gate

Seek **existing** Indian close-range, scale-documented imagery from dataset authors or college pavement labs before planning a collection campaign. No new local training campaign is assumed. Do not use generic Indian dashcam crops as scaled chip labels.

Reserve the eventual first Indian camera pilot as a deployment validation exercise. If it fails, either obtain permission/data for a separate adaptation set and collect a fresh independent test, or narrow the claim to the public benchmark. Foreign-only chip performance must never be labeled “validated for Indian roads.”

## 6. Data preparation, human review, and leakage prevention

### 6.1 Admission checks before training

For each admitted dataset/version, produce a machine-readable manifest and a human sign-off:

1. **Provenance:** original URL, version/date, archive checksum, exact reuse terms, upstream parents, and acknowledgement requirements. Separate code, weights, images, and annotations. Paper open access is not automatically permission for dataset redistribution.
2. **File integrity:** decode every image; check empty/truncated files, dimensions, channels, EXIF orientation, unexpected color range and mismatched file types. Record failures rather than silently skipping them.
3. **Annotation integrity:** pair images with labels; check class IDs, polygon validity, mask dimensions, instance IDs, bounds, and image–mask alignment after orientation correction. Empty labels are reviewed as possible valid negatives, not deleted automatically.
4. **Duplicate ancestry:** exact hashes, perceptual similarity, filename/sequence lineage, resized/rotated copies, and cross-dataset nearest neighbors. Manually review suspicious pairs. Similarity thresholds are detectors, not guarantees.
5. **Sampling bias:** count original scenes, roads, sessions and conditions, not just tiles. Check whether sources contain only damaged images, only sunny imagery, or different cameras for different classes.
6. **Visual audit:** inspect at least 50 varied image/overlay pairs per proposed source, or all if smaller; include negatives and each relevant class. Audit more where failures cluster.
7. **Scale audit:** label each file `source_calibrated`, `rig_calibrated`, `reference_measured`, or `unscaled`. No blanket mm/pixel value copied across dataset versions.

Admission is task-specific: an image can be excellent for pothole detection and unusable for chip counting.

### 6.2 Freeze splits before cropping or augmentation

Construct a grouping graph using physical road/site, capture sequence, adjacent-frame relationships, original parent image, and duplicate clusters. A connected group belongs to only one split. Holding a later session from the same physical patch in test does not make it an unseen-road test.

Use approximately 60/20/20 train/development/test **by groups** when enough independent groups exist; adjust to class support rather than forcing percentages. If road IDs are missing, infer conservative groups from sequences and visual neighbors and describe the result as group-held-out, not verified road-held-out.

Maintain separate evaluation manifests:

- `aggregate_public_test`: reviewed chip/gap annotations from untouched public groups.
- `distress_india_test`: Indian distress groups excluded from all training and tuning.
- `india_challenge_test`: wet/shadow/unsupported-surface cases, kept separate from ordinary accuracy.
- `live_india_acceptance`: eventual real-camera footage, unseen by training/calibration of the condition model.
- Optional foreign cross-source test: useful diagnosis, never the headline local result.

Use grouped development folds for model selection and threshold fitting. Keep the final test untouched. Fit normalization, feature selection, reference statistics, anomaly memory banks, augmentation policies and score mapping on training/development only. Check pretrained road-specific weights for training-set overlap; a generic ImageNet encoder has clearer ancestry than an unknown “road model” download.

When final testing reveals a failure and the model is changed, the exposed set becomes development data. Obtain a fresh test group for a new headline result. Retain old failure results in the report.

### 6.3 Annotation protocol and workload

**Pilot:** 10 double-annotated aggregate crops; 20 Indian distress examples and negatives; 20 independently rated condition examples. These numbers are a starting budget, not adequate final sample-size claims.

**First useful training round:** aim for 80–150 carefully selected aggregate crops from at least 30 distinct parent images, roughly 150–300 Indian distress images with masks where labels are absent, and 150–250 reviewable condition patches. Keep disjoint evaluation material. Increase the number of independent roads/parents before multiplying crops from the same image. Final volume follows learning curves and disagreement, not a fixed magical minimum.

Annotation definitions:

| Label | Rule |
|---|---|
| `visible_aggregate_instance` | One separable exposed particle region. Touching particles are split only when a boundary is visible. Buried stones are not guessed |
| `ignore` | Unresolvable boundaries, glare, water, occlusion, ambiguous surface or missing label coverage; ignored by loss and relevant measurement denominator |
| `valid_surface` | Usable road plane excluding marker/non-road/occlusion; geometry validity and appearance validity recorded separately |
| `crack`, `pothole` | Actual visible footprint; not the enclosing box. A narrow chip-view crop may not reveal global crack orientation |
| `repair_or_patch` | Context flag initially. A repaired patch is not automatically bad |
| `surface_family` | Only use documented/recognizable families. Otherwise `unknown`; do not infer exact mix grade from one image |
| `human_condition` | Visually sound / intermediate or uncertain / visibly deteriorated, with reasons, independent of model output |

Review at least 20% of routine annotations independently and every ambiguous case. For condition labels, use two blinded raters plus a third adjudicator. Seek a civil/pavement specialist for the rubric and a small disputed subset if available; student consensus is useful but not expert certification.

SAM2 may accelerate training-label proposals **after** the unaided pilot. Review every accepted proposal. Prefer independent manual annotation for the test set to avoid a benchmark reproducing the same segmenter's mistakes. The [SAM2 repository](https://github.com/facebookresearch/sam2) supplies tools, not road-aggregate ground truth.

For known-good references, reviewers must inspect the actual patch; “no annotated crack” is insufficient. Keep uncertain examples out of the good reference. Separate apparent texture health from whole-road safety or engineering condition.

## 7. Geometry and physical measurements

### 7.1 Two valid scale paths

**Public planar images:** preserve documented x/y GSD and transformation history. Pure cropping preserves scale; resizing changes it. For x/y scale `sx, sy` in mm/pixel, area is `valid_pixels × sx × sy / 1,000,000` m². Do not force a uniform physical scale on uncalibrated dashcam imagery.

**Live camera:** calibrate intrinsics/distortion at fixed resolution, focus, enclosure and stabilization state; collect about 15–25 varied board views. Estimate the local road-plane mapping using measured correspondences. Check independent distances that were not used to fit it. A calibration marker need not remain in every operational frame when a stable rig profile is valid.

For undistorted images, if world-to-camera pose is `[R|t]` and the local road plane is `Z=0`, `H = K[r1 r2 t]` maps plane coordinates to image coordinates. Invert and normalize to measure on the plane. See [OpenCV homography documentation](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html). Camera attitude relative to gravity alone does not give the changing camera-to-road plane relationship.

A flat-plane mapping yields projected dimensions. Pothole walls, water depth and volumetric loss remain unmeasured. Large relief or changing mounting geometry invalidates affected measurements.

### 7.2 Resolution and motion gates

Initial live target: approximately 0.2–0.3 mm/pixel in the useful ROI **if the camera supports it**; use a smaller footprint rather than an invented upsampled resolution. Public datasets may support only coarser features. Evaluate the common resolvable size range; do not compare public counts of coarse stones with live counts including many finer stones.

Example calculation, not a hardware promise: 500 mm across 1920 useful pixels gives about 0.26 mm/pixel. A 1 mm gap spans under four pixels before optical blur, already a difficult measurement.

Approximate along-track exposure displacement is `v_mps × exposure_s × 1000` mm. At 5 km/h and 1/2000 s this is about 0.69 mm, or about 2.7 pixels at the example scale. High FPS does not remove blur from a long exposure. Test stationary first, then very slow movement; improve light/exposure before claiming higher speed. These are geometric calculations, not observed performance.

Reject/suppress affected metrics for decode failure, absent scale, excessive blur, clipping/glare, invalid surface, changed zoom/crop, unstable plane or inadequate source resolution. Calibrate thresholds against labeled accepted/rejected examples per camera; one universal Laplacian threshold can mistake smooth good asphalt for blur.

Preserve original images. Avoid generative restoration or super-resolution in the measurement path. Apply mild, versioned illumination normalization only if repeatability improves; it must not remove meaningful appearance differences.

### 7.3 Feature definitions

| Feature | Definition | Important restriction |
|---|---|---|
| Count density | `N / A_eligible_m2` | Visible particles above the validated minimum size; show N and A beside density |
| Particle size | Equivalent diameter `sqrt(4 × projected_area_mm2 / pi)` | 2D exposed appearance, not sieve-size/internal gradation |
| Aggregate coverage | Union of aggregate masks / eligible area | Use union, not a sum that double-counts overlapping masks |
| Gap | Visible boundary-to-boundary separation between adjacent particles | Not binder thickness, void depth, or the width of every dark region |
| Texture proxy | Small feature set at fixed physical offsets: GLCM contrast/homogeneity, gradient energy, LBP summary | Unitless; depends on scale and lighting; never relabel as mm roughness |
| Crack density | Metric skeleton length / inspected surface area | Skeleton adjacency distances must account for diagonal steps and scale |
| Defect extent | Mask's projected area / valid inspected area | Boxes provide localization only; no box-derived precise area |
| Distribution | Fraction of spatial subcells affected, repeated along-route observations, observed lateral position | Do not claim wheel-path or full-lane coverage without actual geometric support |

Use an interior counting ROI with a context margin. Count instances whose centroid lies inside that ROI, with enough external context to identify the instance. Truncated/ambiguous objects enter the documented ignore policy. Record the minimum measurable diameter; changing it changes density and requires a new reference version.

For gaps, use a documented local medial-axis or adjacent-boundary method on the non-aggregate region. Keep only sites whose opposing nearest boundaries belong to distinct confident instances. Exclude ROI edges, broad open regions, distress and ignore masks. Report median/IQR/p90 of qualifying separations and the valid sample count. Do not treat `2 × distance transform` everywhere as a physically meaningful inter-chip gap.

**Denominator safeguard:** record total observed road area, texture-eligible intact area, ignored area, and distress area separately. Removing a pothole from the texture denominator must not remove its damage contribution. If the mask selects only easy clean pixels, report the fraction excluded.

### 7.4 Error reporting

Compare public-image metrics with independently annotated masks/endpoints, but label this **annotation agreement using source scale**. It is not independent proof of the source's physical calibration. Live metric validation needs held-out physical dimensions.

Track scale and boundary uncertainty separately. A small relative linear-scale error approximately doubles in area, so density uncertainty is also affected. Report practical precision: a dataset around 1 mm/pixel does not justify hundredths-of-a-millimeter gaps. Use per-parent/site summaries and intervals; do not bootstrap neighboring crops as independent roads.

## 8. Models and training: a deliberately small stack

### 8.1 Aggregate engine

**Baseline:** OpenCV/scikit-image illumination normalization, gradient/threshold markers, morphology and marker-controlled watershed. Tune on development data; measure split/merge errors and count bias.

**Selected learned challenger:** a small U-Net with a pretrained ResNet18 encoder, predicting aggregate interior, boundary, and background with an ignore mask. Convert the foreground/interior predictions into instances with fixed, validated watershed postprocessing. This targets dense touching particles without requiring a large per-object detection pipeline. [Segmentation Models PyTorch](https://smp.readthedocs.io/en/latest/models.html) provides the basic U-Net/encoder implementation; our instance reconstruction still requires testing.

Train from human instance labels transformed into semantic interior/boundary targets. Derive the final particle mask using foreground support, not shrunken interiors alone; otherwise the training boundary band artificially widens measured gaps. Measure geometry after reconstruction at the original metric resolution.

Start with native-resolution tiles around 512×512 pixels, context margins, and overlap blending. Size tiles around the resolved particle scale and memory budget, rather than shrinking a whole frame until chips vanish. Merge instance IDs at tile boundaries and count each particle once.

If the challenger cannot outperform the classical baseline on unseen parent groups, keep the baseline. If it repeatedly merges stones despite good labels, test **one** instance-model alternative: torchvision Mask R-CNN with appropriate dense-instance limits. [Torchvision fine-tuning guidance](https://docs.pytorch.org/tutorials/intermediate/torchvision_tutorial.html) is a supported starting point. SAM2 remains annotation assistance; it is not automatically the production winner.

### 8.2 Distress engine

Use a separate small U-Net/ResNet18 segmentation model for broad crack and pothole classes. This is separate weights from aggregate segmentation, even if code is shared. Fine-tune on the reviewed Indian mask subset; optional foreign mask pretraining is retained only if it improves Indian development results.

If mask annotation cannot be completed immediately, a small YOLO detector on RDD India is a temporary localization baseline. It does not satisfy precise defect-area measurement. Do not build both as mandatory permanent branches unless evaluation establishes a need. [Ultralytics label documentation](https://docs.ultralytics.com/datasets/segment/) distinguishes segmentation polygons from boxes.

Ravelling/bleeding/polishing remain human-reviewed appearance flags until discriminative labels and local tests justify automatic classes. A regular repaired patch is not automatically a defect. Do not add speed-breaker-specific modeling merely because a dataset contains that label; exclude/flag unsupported geometry.

### 8.3 Practical Colab recipe

- Lock Python/PyTorch/library versions after a successful minimal notebook; save the environment and dataset manifests with each run.
- Start with pretrained encoder frozen for a few epochs; then unfreeze gradually at a lower learning rate. Use AdamW, a small development search, and best-development checkpointing. No exhaustive architecture sweep.
- Use mixed precision where supported, batch size determined by actual runtime memory, and gradient accumulation if needed. Save model, optimizer, scheduler, epoch and random states to persistent storage.
- For semantic masks, begin with cross-entropy plus Dice (or BCE plus Dice for a binary head); handle ignored pixels explicitly. Use class-aware sampling without erasing genuine negative prevalence from validation.
- Apply modest rotations/flips and bounded exposure/compression changes. Restrict transformations that destroy geometry or semantic orientation. Any resize changes scale metadata. Avoid elastic warps/CutMix for metric ground truth unless transformed measurements are rigorously recomputed.
- Retain hard negatives: shadows, sealed lines, stains and non-distress surface texture. Do not train only on damage-centered crops.
- Track three curves: training loss, group-held-out segmentation/count performance, and acceptance/rejection rates. A model that rejects difficult scenes is not scored only on its easiest surviving images.

Colab resources and session lengths are variable; it is a training environment, not the required always-on production endpoint. Persist checkpoints and avoid a live demonstration that depends on a notebook tunnel. [Colab FAQ](https://research.google.com/colaboratory/faq.html)

### 8.4 Overfitting, underfitting, and domain shift

| Observation | Likely issue | First action |
|---|---|---|
| Training strong, unseen groups weak | Overfitting, duplicates, camera/site shortcut | Audit lineage; freeze more encoder layers; reduce capacity; add diverse reviewed training parents |
| Both training and development weak | Bad labels/preprocessing, unresolved detail, underfitting | Overfit a tiny clean batch as a diagnostic; inspect alignment and visibility before increasing model size |
| Good IoU but biased counts | Merged/split particles, tile duplication | Inspect instance errors and postprocessing; optimize counting, not just semantic IoU |
| Foreign results good, India poor | Domain shift | Use Indian distress development data; test grayscale/scale normalization; obtain separate local adaptation evidence if permitted |
| Public chip count works, live chip count shifts | Resolution/minimum-size mismatch or rig domain change | Match physical scales and count definitions; audit calibration and supported reference domain |
| All images predicted good/background | Imbalance or missing negatives/positives | Inspect per-class recall, sampling and loss; do not celebrate pixel accuracy |
| Training very unstable | Tiny batches, too-high LR, corrupt masks | Inspect batch statistics, lower LR, verify inputs; do not launch another large model |

## 9. Known-good learning and the final quality index

### 9.1 Separate comparison, grading, and trust

The reference model learns from reviewed good patches in a supported surface/camera-scale domain. Begin with 5–8 stable features, not dozens of correlated descriptors: count density, median particle size, aggregate coverage, gap median and tail, one or two texture indicators, and a spatial variation term.

Fit robust medians and scales on training good groups. Compare a simple normalized-deviation baseline with shrinkage Mahalanobis distance. Choose using development performance and stability. With very few independent groups, prefer the simple reference; a fitted covariance matrix is not extra information.

PatchCore through [anomalib](https://github.com/open-edge-platform/anomalib) is optional only after the reference baseline works. Its memory bank must contain training-good images only. The heatmap means visual difference, not a physical defect class or certified severity.

Reference domain compatibility is checked separately from damage: an unusually damaged **supported** asphalt patch must not be rejected as an unknown material merely because anomaly distance is high. Use metadata, visible material cues and a reviewed domain gate; reserve abstention for unsupported input or insufficient evidence.

### 9.2 Recommended scoring policy

Use two explainable groups: texture deviation `T` and observed distress burden `D`. Keep inclination and confidence separate.

1. Derive `T` from the known-good comparator, retaining signed feature deviations for explanation.
2. Derive `D` from measured defect fractions/length and observed distribution. The definitions and units must be stable before fitting a score.
3. Fit a small regularized, preferably monotone model of human-rated condition using `T`, `D`, and at most one distribution term. Use grouped development predictions for calibration. Compare it with a transparent fixed-rule baseline.
4. If there is adequate assessed data and calibration support, map estimated `P(visually bad | supported evidence)` to `SQI = 100 × (1 - P_bad)`. Describe it as a model-based visual condition index; show calibration reliability, not only AUROC.
5. If data do not support probability calibration, use a **provisional reference-deviation index** with a documented monotone mapping and review label. Do not market it as a validated Good/Bad condition score. Obtaining rated examples remains a completion task.

Do not use arbitrary 0.5/0.4/0.1 weights or copied 70/40 thresholds as final truth. Select Good/Bad thresholds on development evidence with the tradeoff between false reassurance and false alarms shown. Intermediate/disputed cases can be `review`; report their frequency. Never force Good/Bad for unreadable or unscaled inputs when the model requires metric features.

Mandatory features missing → `score=null`, unless a separately evaluated partial-input policy exists. Do not silently renormalize weights or count absent distress as zero. If texture segmentation improves and the feature distribution changes, version/revalidate the reference and score mapping.

### 9.3 Explanations and confidence

Show measured feature values, reference median/range, and direction of deviation. Signed z-scores are explanations of differences, not exact additive contributions to a correlated Mahalanobis distance. Use the actual final score model when claiming contribution.

Record confidence components rather than inventing a product of unrelated numbers: geometry validity, annotation/model validation domain, image quality, feature completeness, and sampling coverage. Use descriptive states initially; only display a probabilistic confidence if empirically calibrated.

A possible severe defect triggers a separate inspection-priority flag with its evidence. It must not disappear under a good median score, and must not automatically prescribe structural repair. Humans decide whether an uncertain texture represents wear, a different mix, or lighting.

## 10. Inclination: implement an honest minimum

Keep `grade_percent`, `grade_deg`, `source`, `uncertainty`, `capture_time`, and `validity` separate from surface condition. `grade_percent = 100 × tan(angle)` for a valid longitudinal grade angle.

**First supported path:** import a human-verified supporting measurement at a known sample position, for example a calibrated inclinometer/phone-level reading on a rigid straightedge aligned with the road's longitudinal plane during a safe controlled check. Validate zero offset and repeatability; distinguish longitudinal grade from crossfall. This is supporting sensor data, not image-only estimation.

**Automatic live path, conditional:** rigid camera/IMU alignment, synchronized stationary or quasi-static measurements, and a validated relation between camera and local road plane. A measured plane normal plus gravity can yield inclination; a moving phone's pitch alone cannot. Acceleration, suspension motion and mount drift require invalidation rather than subtraction of one flat-road offset.

Do not use noisy consumer GPS heights or Google Elevation as fine-scale grade ground truth. Existing driving poses can test plumbing, but vehicle attitude is not an independent pavement-grade label. A homography estimated from a metric target does not automatically remain valid through changing road/camera pose.

Inclination remains a formal requirement until measured or explicitly exempted by the judge. If only reference sensor entry is implemented, state that capability precisely; it is not continuous automatic slope measurement. No unvalidated grade penalty enters SQI.

## 11. Final application architecture and tools

### 11.1 Chosen deployment

```text
Public dataset preparation + reviewed annotations
                 |
          Colab offline training
                 |
       versioned model artifacts in S3
                 |
New image / actual live camera / explicitly labeled replay
                 |
      capture adapter + timestamps + calibration ID
                 |
      AWS FastAPI API -> private S3 raw assets
                 |
       persistent job state + inference worker
                 |
      QC -> geometry -> aggregate + distress
                 |
        physical features + known-good model
                 |
       deterministic score and evidence record
              /                    \
  React inspector UI           Bedrock explanation
  + Google Maps                from approved facts
              \                    /
           versioned assessment/report
```

**Choose one deployment path:** React/Vite frontend; FastAPI API and one worker on a modest AWS EC2 instance; SQLite job/result metadata on persistent EBS; private S3 for images, models and reports; Bedrock via the server's IAM role; Google Maps JavaScript in the frontend. Serve the initial frontend through the same HTTPS application host to reduce moving parts. Move static assets to S3/CloudFront later only if useful.

Begin CPU inference with the classical/small-model pipeline and benchmark it. If throughput is insufficient, first reduce the processing cadence or use validated tiling/batching; then size an AWS GPU instance only if required and budget/quota permit. Do not assume a free-tier CPU can provide dense live segmentation at camera FPS. No unquoted hourly-price promise is made here.

Training remains Colab; serving remains AWS. Bedrock is for language inference, not a host for custom U-Net weights. AgentCore, Kubernetes, microservice decomposition, DynamoDB, API Gateway, RDS, and a native mobile application are not required for this first architecture.

### 11.2 Stack and why

| Layer | Selected tools | Reason / fallback |
|---|---|---|
| Core language | Python 3.11 where compatible; locked environment | Stable CV/statistics tooling; pin a tested compatible version |
| CV/geometry | OpenCV, NumPy, SciPy, scikit-image | Calibration, morphology, masks, physical transforms |
| Learned segmentation | PyTorch + segmentation-models-pytorch | Small transfer-learning baseline; classical fallback remains explicit |
| Reference/scoring | scikit-learn, pandas | Robust statistics, regularization, grouped evaluation/calibration |
| Labeling | CVAT or Label Studio; select one after the pilot | Human masks, ignore regions, review workflow; SAM2 proposals optional |
| API/contracts | FastAPI + Pydantic | Validated units/status and common upload/live engine |
| Runtime | Docker on EC2; worker separate from API process | Repeatability; long inference does not block web requests |
| Metadata | SQLite on EBS, one controlled writer initially | Sufficient for a three-person prototype; PostgreSQL only when concurrent load warrants it |
| Assets | Private versioned S3 prefixes | Originals, annotations, models, results, audit artifacts |
| Frontend | React + TypeScript + Vite | Direct Google Maps integration and live job states; avoid rebuilding a second UI later |
| Map | Google Maps JavaScript API | Mandatory integration; use supplied GPS polylines first |
| Narrative | Boto3 Bedrock Runtime Converse API | Mandatory Bedrock integration without agent orchestration |
| Tracking | CSV/JSON experiment ledger, Git commit and hashes | Adequate initially; MLflow optional after reproducibility exists |
| Verification | pytest for units/contracts; evaluation scripts for CV | Test actual failure paths and physical invariants |

### 11.3 Job lifecycle and data integrity

Use `received → validated → queued → processing → succeeded / partial / failed`. Store every transition, attempt count, model version and error reason. Upload completion is not analysis completion.

For direct S3 upload: API allocates an object key and short-lived upload URL; client uploads; API finalizes after checking object existence, expected metadata and size, then creates the job. S3 presigned URLs provide time-limited delegated access; scope them to exact objects. [AWS S3 documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)

Use an idempotency key such as `(session_id, frame_sequence, model_version)` with uniqueness enforcement. Retries must not duplicate segment samples. The worker leases a job with a timestamp; abandoned jobs can be retried after a crash. Persist before acknowledging. Use atomic result writes and keep old result versions when models change.

For live capture, keep a bounded queue. Preserve timestamps and the original capture recording where feasible; discard redundant inference requests explicitly when falling behind. Log received, queued, processed, rejected and dropped counts. Never show a stale frame's score as the current frame result.

### 11.4 Minimum API

| Endpoint | Purpose |
|---|---|
| `POST /v1/uploads` | Allocate private object and upload metadata |
| `POST /v1/uploads/{id}/finalize` | Verify upload and enqueue analysis |
| `POST /v1/sessions` | Create live/replay session with mode, device and calibration |
| `POST /v1/sessions/{id}/frames` | Submit sequence, frame URI, capture timestamps and telemetry |
| `POST /v1/sessions/{id}/finish` | Close capture and finalize aggregate results |
| `GET /v1/jobs/{id}` | Poll durable processing status |
| `GET /v1/samples/{id}` | Return metrics, overlays, reasons and measurement validity |
| `GET /v1/sessions/{id}/segments` | Return sampled route bins and coverage |
| `POST /v1/reports` | Generate versioned factual report and Bedrock wording |
| `GET /v1/health` | Model, storage, worker and integration readiness |

### 11.5 Canonical record

Every sample carries:

```text
identity: sample_id, session_id, source_dataset/version, parent_id, sequence_id
provenance: file_sha256, original_uri, license_record, split_group
time: captured_at_utc, monotonic_capture_time, received_at, processed_at
camera: camera_id, calibration_id, width/height, exposure, crop/zoom state
location: lat/lon, accuracy_m, route_distance_m, distance_source, is_simulated
geometry: scale_source, sx/sy_or_H, valid_roi, observed_area, error_bound/status
quality: accepted/limited/rejected, reason_codes, ignored_fraction
features: value, unit, status, estimator_version, evidence_id for each metric
assessment: SQI_or_null, Good/Bad/review/unknown, reference_id, policy_version
coverage: frame_interval, inspected_strip, unique_area_or_null, coverage_method
audit: model_hash, code_commit, config_hash, reviewer_corrections
narrative: factual_input_hash, Bedrock_model_id, status, generated_at
```

Use enums and explicit units. `null` is unknown; `0` is measured absence. Human edits create a new reviewed version rather than overwriting raw predictions. Comparisons across model/reference versions need clear labeling.

### 11.6 Mandatory service readiness and cost controls

Run an AWS/Bedrock/Maps smoke test early, in parallel with the data pilot: one private image upload/read, one small authorized Bedrock request, and one Google map with an owned sample marker. This catches account and regional availability issues before scientific work is complete.

Use IAM roles for AWS, no permanent keys in frontend or Git; keep buckets private; validate file size/type; protect the shared app with authentication; store secrets server-side; restrict the Maps browser key by site and API. Maps requires billing and an API key; budget controls and restrictions should be configured from the start. [Google setup guidance](https://developers.google.com/maps/documentation/javascript/troubleshooting)

Choose a currently available Bedrock model in the chosen AWS region after a small output-quality/cost check; record its exact model ID, not a guessed permanent product name. Configure call/time limits, retries with backoff, AWS/GCP budget alerts, storage lifecycle and compute shutdown when idle. Alerts are not guaranteed hard spending caps. Budget remains a team decision before provisioning paid resources.

## 12. Live route aggregation, Google Maps, and Bedrock

### 12.1 Route truth and sample coverage

Acquisition can run continuously while inference samples more slowly. For footprint length `L`, speed `v`, and processing frequency `f`, center spacing is approximately `v/f`. Continuous accepted-strip coverage requires that spacing not exceed the usable footprint, with failures and overlap accounted for. Otherwise label it sampled inspection.

Start with 50 m reporting bins; reduce only when localization and sample density justify it. GPS accuracy can exceed a 10 m bin. Keep GPS time/accuracy and camera time synchronized; frame upload time is not capture time. Route distance should follow the traveled path, not straight-line distance from the origin.

Minimum aggregation:

- Group overlapping/near-duplicate frames before calculating evidence weight.
- Use reliable relative motion or conservative capture spacing to estimate unique coverage. GPS alone cannot register adjacent aggregate patches.
- Where registration is unreliable, show observed sample area and `unique_area=unknown`; do not sum overlapping patch areas as unique coverage.
- Aggregate per spatial sub-bin to limit the influence of frames captured while stopped. Display median score, lower-tail score when enough samples exist, defect flags, and support count.
- Keep severe observed defects visible alongside median score. A single suspicious frame is an evidence flag, not proof the entire segment is damaged.
- Report inspected strip width and sampled length; road-wide area coverage requires lane width and actual lateral coverage.

Color assessed samples or bins with clear “sampled condition” labels. Unsampled/insufficient regions remain neutral. Do not interpolate good condition across a missing stretch.

### 12.2 Google Maps use

Draw real GPS-derived paths and segment overlays. Marker cards open original image, mask, source, measurement validity and explanations. Maps supplies geographic display, not measurement scale or defect training images.

No Routes/Roads/Elevation API is needed just to draw supplied coordinates. Add map matching only after real GPS errors warrant it, and preserve both raw and matched coordinates. A planned route can be displayed as planned; it cannot supply actual frame locations.

If public images lack GPS, show an unlocated image assessment. A simulated route is allowed only as an explicitly separate integration demo, never represented as an Indian survey or used for geographic validation. Foreign images retain their actual source geography.

If internet fails, show route-distance plots and cached **own assessment data** in a local/offline evidence view. Do not assume Google map tiles can be bulk cached. This backup does not remove the requirement to demonstrate the actual Google Maps integration under normal conditions.

### 12.3 Bedrock behavior

Send compact structured measurements and permitted interpretation labels to Bedrock using [Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html). Do not send the whole training archive or ask an LLM to estimate counts, gaps, condition weights, or damage dimensions.

Return a constrained structure such as `summary`, `evidence_ids`, `limitations`, and `inspection_actions`. Validate schema and evidence references. Prefer rendering numbers directly from the factual record instead of allowing free-form regenerated numbers; reject unsupported claims. Dataset text and image metadata are untrusted content, never instructions to the narrator.

Generate once per finalized sample report or segment, not every camera frame. Cache by assessment/version hash. If Bedrock times out or validation fails, use a deterministic factual template and clearly record fallback status. Acceptance requires at least one real successful Bedrock path plus the tested fallback; templates alone do not fulfill the mandatory integration.

Recommendations are inspection actions: review this crack, recapture a wet patch, verify possible ravelling, or prioritize site inspection. Do not prescribe sub-base reconstruction, exact repair materials, cost or safety certification from RGB alone.

## 13. Validation and release gates

### 13.1 Tests that establish the claims

| Claim | Test / ground truth | Report |
|---|---|---|
| Input and label integrity | Full decode/alignment audit and reviewed sample overlays | Failures, exclusions, source versions |
| Physical scale | Held-out measured target dimensions; source-scale lineage separately | Length MAE, median/p95 relative error, image position and geometry validity |
| Chip identification | Human-reviewed independent instance masks | Instance precision/recall, count bias, relative count error, merge/split errors |
| Gap measurement | Independent endpoint annotations and physical gap target where available | MAE, inter-rater error, lower measurable limit, suppressed fraction |
| Distress segmentation | Untouched Indian masks/negatives | Class precision/recall, Dice/IoU, missed defects, false positives per valid area/frame |
| SQI and Good/Bad | Blinded reviewed condition labels | Confusion matrix, balanced accuracy, bad recall, false-good rate, calibration and review rate |
| Reference usefulness | Against simple texture-only and distress-only baselines | Incremental value of count/gaps/reference, per-domain failures |
| Lighting stability | Naturally varied examples plus controlled repeat captures when camera acquired | Feature/score drift and reject rate; synthetic stress separate from natural tests |
| Speed robustness | Same actual setup under stationary and controlled movement | Scale/count/gap error, accepted fraction and latency vs measured speed |
| Indian transfer | Independent public Indian test plus live acceptance set | Results by source/site/camera; foreign results listed separately |
| Route validity | Known session sequence/time and position evidence | Sample/unique coverage, duplication, missing GPS, bin support |
| Service reliability | Repeated uploads, retry/crash, network and Bedrock failure | No duplicate counts, durable jobs, correct fallback labels |

### 13.2 Provisional numerical targets

These are proposed engineering thresholds to freeze **after the pilot and before final testing**, not achieved numbers or sponsor requirements:

- Scale: aim for median held-out length error ≤5%; publish p95 and exclude unstable ROIs. Area error requires a separate check.
- Visible particle count: aim for median relative error ≤15% on resolvable independent patches; report small-N cases with absolute error and publish the full distribution.
- Gap: declare the smallest reportable gap and target error at that scale; do not pass when uncertainty is comparable to the claimed separation. A possible starting rule is error ≤25% of the minimum claimed width, subject to human agreement and optics.
- Distress: compare with the classical/detector baseline on Indian groups and report each class. A single pooled IoU cannot conceal poor pothole recall.
- Classification: start with a target of ≥0.80 balanced accuracy and ≥0.85 bad recall on supported rated examples, with intervals and rejection rate. These values are discussion targets; tiny tests cannot certify them.
- Live: establish p50/p95 capture-to-result latency and sustainable accepted samples/s. A provisional UI target is p95 ≤5 seconds at the chosen cadence; separately prove whether cadence provides continuous strip coverage.

If targets are infeasible, improve sensing/data or narrow the **declared** operating envelope. Do not lower targets after seeing final-test results to manufacture success. A failed gate can be a useful experimental result but is not a completed requirement.

### 13.3 Avoid misleading evaluation

- Report parent/site counts with every score. Thousands of tiles from a handful of roads do not establish national performance.
- Use group/site bootstrap intervals where enough groups exist; with very few groups, show per-group results rather than spurious precision.
- Audit the rejected set: report performance on accepted examples **and** the fraction excluded. Check whether bad roads are rejected more often than good ones.
- Include true intact Indian negatives. A detector tested only on damage images cannot establish false-alarm behavior.
- Compare masks and dimensions separately. Centerline annotations can support crack presence while being invalid width ground truth.
- Repeated processing of the same image tests deterministic software behavior, not robustness to real lighting or camera movement.
- Artificial blur/brightness sweeps test sensitivity; they do not establish actual vehicle-speed or monsoon performance.
- Keep rating disagreement visible. Do not fit a complicated score that merely memorizes one teammate's aesthetic preferences.

### 13.4 Minimal software tests worth keeping

Test coordinate-transform direction/units, resizing scale updates, known polygon area, density denominator, border counting, tile deduplication, ignored-pixel handling, null-versus-zero behavior, score policy versions, route overlap accounting, idempotent retries, and Bedrock evidence validation. Synthetic geometric shapes are appropriate here because the question is arithmetic correctness, not real-road accuracy.

## 14. Phase-by-phase execution and ownership

| Phase | Primary owner | Work and deliverable | Exit gate / fallback |
|---|---|---|---|
| **0. Scope and dependencies** | All; C coordinates | Confirm chip-boundary/roughness definitions, live/moving requirement, camera access plan, budget/account readiness; AWS/Bedrock/Maps smoke test | Live access route and paid-service feasibility identified; unresolved requirements stay explicit |
| **1. Data admission and visibility** | B, supported by A | Sample files, provenance, scale checks, duplicate groups, pilot annotations; request gated datasets | Humans can identify the intended features at a verified scale; otherwise switch source or declare blocked feature |
| **2. Real image-to-measurement slice** | A | One actual image → QC → metric ROI → classical masks/count/size/gaps → versioned JSON | Independent count/scale checks; no hard-coded demo metrics |
| **3. Minimal AWS upload application** | C | Private S3 upload, jobs, API and simple React evidence screen | User uploads a new file, sees actual result or explicit invalid reason; retries safe |
| **4. Frozen data and learned challenger** | B + A | Reviewed training/dev/test groups; U-Net experiment; Indian distress mask subset | Best method selected on development groups; classical retained when better |
| **5. Reference and SQI** | B | Known-good profile, reviewed condition rubric, small calibrated scoring policy, reasons | No leakage; score outperforms a stated baseline or remains provisional |
| **6. Actual camera and live transport** | C + A | Acquire device, calibrate, transmit new frames, benchmark AWS inference and bounded queue | Actual live capture proven. Replay cannot pass this gate |
| **7. Local route, inclination, integrations** | C; A validates geometry | Indian GPS route, sample coverage, Google Maps overlays, sensor-grade path, Bedrock report | Real coordinates and condition evidence; grade measured or exemption obtained; successful mandatory integrations |
| **8. Independent acceptance** | B coordinates; all review | Frozen public Indian tests plus new local camera tests, speed/light/domain checks | Requirements pass within a stated envelope; failure evidence preserved |
| **9. Release and demo** | All | Frozen artifacts, runbook, validation report, credits, actual live demonstration and labeled backup | Any teammate can run the complete path; no unsupported claims |

Camera acquisition and platform smoke tests begin in Phase 0, not Phase 6. Phase 6 is integration/completion, not the first attempt to find hardware. Data/model work, cloud scaffolding and camera access can progress concurrently with shared contracts; no person should work against an invented schema.

**Member A:** image quality, geometry, aggregate extraction, physical validation.

**Member B:** provenance, splits, human-label workflow, training, reference/scoring, independent evaluation.

**Member C:** camera transport, AWS services, API/jobs, UI, Maps, Bedrock, demo reliability.

All three annotate a calibration set and review failures. B protects final-test files from routine model tuning. A validates metric calculations; C ensures the UI never converts missing data into a green result.

## 15. Fallbacks, sacrifices, and scope limits

| Failure or constraint | Best response | What is sacrificed / still missing |
|---|---|---|
| Preferred scaled dataset inaccessible | Try the documented fallback, request original files/terms through team | Access latency; do not start blind full training |
| Chips visible but gaps too fine | Report count/size and only resolvable gap range; seek finer existing imagery | Full gap requirement remains open if judge needs finer detail |
| Humans cannot separate particles | Improve source/resolution or obtain existing expert imagery | Texture-only output is a partial feature set, not successful counting |
| No suitable Indian calibrated training imagery | Use foreign data for development, test transfer on acquired Indian camera | No Indian chip-performance claim before local validation |
| No live hardware/access | Escalate loan/rental/organizer access; continue software independently | Required live demo is blocked; replay is not completion |
| Slow AWS inference | Lower requested cadence, optimize small model, then consider GPU | Real-time latency/coverage tradeoff must be displayed |
| Colab session ends | Resume persistent checkpoints | Training time lost, not model/data provenance |
| Poor instance model | Keep validated classical baseline; add better labels | Less sophisticated model, not weaker honesty |
| Poor distress masks | Detection-only temporary baseline; manually label Indian masks | Precise defect-area requirement not complete yet |
| Public-to-live domain shift | Fix geometry/scale first; use separate adaptation and new test if permitted | Cannot promise public-only training will generalize |
| Missing scale on judge upload | Image-level evidence only; request calibrated profile/reference | No physical metrics; no guessed cm |
| Missing GPS | Unlocated assessment and distance view if distance exists | Geographic map evidence missing for those samples |
| Unreliable grade | Supporting measured grade or explicit exemption | No continuous auto-grade claim |
| Bedrock/network unavailable | Deterministic evidence report; retry later | Mandatory integration still needs a successful normal-path demonstration |
| Map unavailable | Local evidence list/distance plot | Not a permanent replacement for required Google Maps |
| Human raters disagree | Adjudicate or use review/uncertain label | Fewer training labels; better truthfulness |

**Deliberate sacrifices:** global generalization, full-lane coverage from one narrow view, high-speed operation before tests, millimeter gaps beyond the optical limit, exact physical roughness/depth, automatic repair design, rich multi-agent chat, native mobile app, many simultaneous models, and large benchmark downloads without a demonstrated need.

**Keep as options:** a better camera/global shutter, one instance-model alternative, PatchCore, an additional asphalt reference family, AWS GPU inference, PostgreSQL, map matching, independent physical texture testing, and local adaptation data if access later changes. Each option must address a measured failure.

**Defer without special-case modeling:** humps/speed breakers, unusual road furniture, snow/ice, night operation, flooded pavement, full 3D reconstruction, nationwide mix taxonomy. Ordinary invalid-input and unknown-surface handling remains necessary; a dedicated model for every exception does not.

## 16. Repository and required implementation artifacts

```text
roadsight-ai/
  README.md
  pyproject.toml + tested lockfile
  configs/                 # camera, features, data mapping, scores, deployment
  src/roadsight/
    schemas.py
    ingestion/             # upload/live/replay adapters and timestamp handling
    quality/               # validity and supported-domain checks
    geometry/              # calibration, scale, transforms, uncertainty
    aggregate/             # classical, learned masks, instances, measurements
    distress/              # segmentation and physical extent
    reference/             # good-only profiles and comparisons
    scoring/               # calibrated policy and deterministic reasons
    routes/                # grouping, coverage, geolocation, segment summaries
    reports/               # structured facts, Bedrock wrapper, exports
    api/                   # FastAPI, authorization, durable jobs
  web/                     # React/TypeScript + Google Maps
  training/                # reproducible Colab notebooks and shared Python code
  data_manifests/          # provenance, parent groups, frozen splits; no secrets
  annotation_guides/
  eval/                    # per-task and India/live acceptance evaluations
  tests/
  infra/                   # Docker and one deployment/runbook path
  reports/                 # actual experiment outputs and validation
  demo/                    # approved examples and labeled replay backup
```

Store raw data, masks and models outside Git in controlled local/S3 storage. Keep manifests and reproducible transformations in Git. Notebook outputs do not substitute for a rerunnable training/evaluation entry point.

Required artifacts by completion:

1. Data admission/provenance register and license/attribution inventory.
2. Annotation guide and independent review records.
3. Frozen split manifests including original/duplicate lineage.
4. Camera feasibility and calibration report, including actual operating envelope.
5. Feature specification with units, denominator rules, minimum resolvable sizes and null behavior.
6. Training/model cards with data ancestry, seeds, weights/config hashes and failure examples.
7. Reference/scoring specification with development procedure and final thresholds.
8. Validation report separating foreign development, public Indian evaluation and live Indian acceptance.
9. API contracts, deployed AWS runbook, service configuration and cost-control notes.
10. Live demo runbook, backup recording, source credits and inspection recommendations.

## 17. Demonstration and final definition of done

Show a genuinely new calibrated image first: raw image, valid region, particle boundaries, N, observed area, count/m², supported gap statistics, texture proxy, distress evidence, score and explanation. Include one invalid/unscaled image so the refusal behavior is visible.

Then show the **actual** camera transmitting new road frames, capture time, result time, accepted/rejected counts and the configured analysis cadence. Display the real Indian route/locations in Google Maps and distinguish observed strip results from uninspected road. Show the Bedrock report grounded in those records. Finish with held-out local metrics and limitations.

If the venue cannot provide a moving vehicle safely, resolve the approved live arrangement beforehand. A stationary live feed proves live ingestion, not moving-vehicle inspection. A video replay proves pipeline replay, not live capture. Name each capability accurately.

The project is complete only when:

- Required features are demonstrated within a declared, validated resolution and operating envelope.
- Known-good comparison and Good/Bad scoring have independent evidence, not only attractive overlays.
- Indian performance is tested and reported separately; claims remain local to tested conditions.
- Actual live access is secured and demonstrated; required moving behavior is confirmed with the judge.
- AWS, Bedrock and Google Maps each work in the normal path, with tested failure behavior.
- Inclination is supported as described or explicitly exempted.
- Dataset rights, leakage controls, uncertainty and human-review decisions are documented.

## 18. Decisions still requiring people or experiments

These are targeted dependencies, not reasons to postpone all work:

| Decision | Who resolves it | What can proceed now |
|---|---|---|
| Exact meaning of chip boundary width and roughness | Judge/team liaison | Implement clearly named 2D spacing, size and texture-proxy definitions |
| Is moving capture mandatory; at what minimum speed? | Judge/team liaison | Camera loan search, static calibration and live transport |
| Is sensor-assisted/checkpoint inclination acceptable? | Judge/team liaison | Grade schema, validated sensor-input route and null behavior |
| Camera/vehicle/site access and budget | Team C + faculty/organizer | Public data and AWS pipeline |
| Public-data access and permitted derived labels | Team B/source owner | Audit accessible samples and rights records |
| Can public imagery resolve the required chips/gaps? | Two human annotators + Team A | Tiny feasibility benchmark before full labeling |
| Local transfer to Indian camera and surface | Independent acceptance exercise | Public-source training with explicitly provisional deployment claims |
| Actual AWS compute/model budget and region | Team C | CPU benchmark and small integration smoke test |

**First implementation milestone:** a real, scale-documented public pavement patch enters the pipeline, returns human-checkable aggregate measurements with honest resolution limits, is stored in private S3, and is displayed in the application. In parallel, secure actual camera access and verify the mandatory service accounts. That combination addresses the highest scientific and delivery risks before the team invests in a large model or polished dashboard.
