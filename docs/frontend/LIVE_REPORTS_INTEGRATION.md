# Live and Reports integration — 16 October 2026

## Use

Start the backend and the production-mode Vite frontend as in the Phase 1 runbook.
Open `/live`, choose **Start camera**, and allow browser camera access. Camera
access needs localhost or HTTPS. This uses browser video only, without microphone
or location access. Frames retain native capture dimensions and are JPEG encoded.
The application creates an actual `live` session and transmits capture timestamps
and frame bytes. It sends at most every five seconds and waits for outstanding
processing before another capture. A 60-second processing wait stops capture
instead of extending the queue. Stop or navigate away to release the camera.

The monitor shows backend counters/timestamps and links to the latest saved
evidence. Completed samples enter this browser's recent-sample history. Camera
permission denial, lost camera / service, and send failures have visible errors.

Open `/reports` and select a completed assessment, or use **Generate report** on
sample detail. Bedrock explanation is optional. The returned saved URL reopens
the report from the backend. JSON download includes the report identity, structured
content, provenance hash and narrative status. No report is generated for unknown
assessments; supplied score fields cannot override stored facts. Missing quality
or distress evidence remains explicit rather than becoming an accepted/zero value.

## Verification and limits

Frontend tests cover camera denial, real-frame request shape, camera shutdown on
unmount, queue backpressure, and report generation/retrieval/fallback display.
Backend tests cover public session status, finished-session rejection, and report
provenance/retrieval. A local replay-mode transport smoke test sent a recorded
image, observed one processed sample and generated/reopened a fallback report.
The browser also generated/reopened a report from the user's saved assessment.
The OpenAPI snapshot and generated frontend types were refreshed together.

Hardware camera permission and road capture still need a human device check.
The replay transport check does not establish live-camera or Indian road accuracy.
Physical scale, grade, GPS, continuous distance coverage and validated scores remain
unavailable in this browser capture flow. Bedrock is unconfigured locally; its
fallback was verified, not an actual Bedrock model call. Recent sample discovery
is scoped to browser history; known saved sample/report URLs remain usable.
