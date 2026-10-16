# Reproducible image-processing evidence

Run from the repository root:

```powershell
python -m eval.processing_evidence --image <road-image> --output-dir <evidence-folder>
```

The command uses `backend.analysis.measure_frame` and the same native-resolution
tile watershed path as uploads. It writes the original file byte-for-byte, PNG
views in source coordinates, the integer candidate-label array, and
`manifest.json`. Use `.runtime/` for local demonstrations; do not commit restricted
source photos or generated copies.

The manifest records image dimensions, mean gray brightness, p99–p1 contrast,
Laplacian-variance sharpness, current quality-gate result and its uncalibrated
threshold flag. It explicitly reports the missing road ROI and physical scale.
Each stage records its input, parameters, purpose, effect, failure mode,
display-only transformation and physical-validation status.

The stages are the current pipeline outputs: Gaussian illumination flattening;
robust percentile normalization; Otsu foreground; configured morphological
opening and small enclosed-hole fill; L2 distance transform; configured
H-maxima or NMS marker selection; stitched watershed candidate labels; and
candidate boundaries over the original image. The integer label map is preserved
as `candidate_labels.npy`; display colors and normalized grayscale are only
visualizations. No source pixels are altered in `original.*`.

**Interpretation:** watershed regions and the downstream pixel-space count are
exploratory algorithm outputs, not verified chip ground truth. Indian RDD boxes
label distress and do not validate aggregate boundaries. Count per m², physical
chip sizes, gap widths in millimetres, a road ROI, and an SQI score remain
unavailable. Do not use this demonstration as an accuracy report or a held-out
test; obtain independent human labels and verified scale first.

The reference India RDD scene also contains sky, vegetation, vehicles and road
furniture. Because the current analyzer has no road ROI detector, its foreground
stage treats these as possible foreground too. This is an observed limitation,
not an acceptable aggregate-quality result.
