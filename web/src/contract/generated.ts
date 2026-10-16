export interface paths {
    "/v1/uploads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Allocate an upload URL
         * @description Create a private upload slot and return a presigned S3 or bounded local upload URL.
         */
        post: operations["create_upload_v1_uploads_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/uploads/{upload_id}/local": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Upload bytes to a private slot (S3-less / local fallback)
         * @description Bounded streaming upload used when no S3 bucket is configured, and by the local/replay demonstration path. The object is written under the media root at the slot's private object key and validated by magic header.
         */
        put: operations["upload_local_v1_uploads__upload_id__local_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/uploads/{upload_id}/finalize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Finalize an upload and enqueue analysis
         * @description Verify uploaded object existence, size and format, record metadata, and enqueue processing.
         */
        post: operations["finalize_upload_v1_uploads__upload_id__finalize_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create a live/replay session
         * @description Start a capture session with explicit mode, camera and calibration.
         */
        post: operations["create_session_v1_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/sessions/{session_id}/frames": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Accept a frame for a session
         * @description Accept one frame with original reference, capture times and telemetry.
         */
        post: operations["ingest_frame_v1_sessions__session_id__frames_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/sessions/{session_id}/finish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Close capture and request aggregation
         * @description Close the capture session and request segment aggregation.
         */
        post: operations["finish_session_v1_sessions__session_id__finish_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Return durable job state
         * @description Return lifecycle state, error reason, attempt count and versions.
         */
        get: operations["get_job_v1_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/samples/{sample_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Return sample evidence and metrics
         * @description Return evidence, metrics, quality, score and narrative status.
         */
        get: operations["get_sample_v1_samples__sample_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/sessions/{session_id}/segments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Return bin summaries and coverage truth
         * @description Return 50 m bin summaries with coverage truth and unsampled stretches.
         */
        get: operations["get_session_segments_v1_sessions__session_id__segments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate factual report and Bedrock wording
         * @description Generate a structured report and optional Bedrock narrative from stored facts.
         */
        post: operations["generate_report_v1_reports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * v1-aligned service health
         * @description State model/worker/storage/integration readiness in the v1 shape.
         */
        get: operations["v1_health_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Liveness probe (no I/O)
         * @description Cheap liveness probe - safe to poll from a target group every few seconds.
         */
        get: operations["health_liveness_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/deep": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Deep dependency diagnostics
         * @description Probe database, S3, Bedrock, the YOLO model and local storage.
         */
        get: operations["health_deep_health_deep_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Root Health */
        get: operations["root_health__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AggregatedMetrics
         * @description Aggregate and distress measurements for a segment.
         */
        AggregatedMetrics: {
            /**
             * Chip Count
             * @description Visible aggregate instance count (null if uncalibrated/unmeasured)
             */
            chip_count?: number | null;
            /**
             * Chip Density Per M2
             * @description Chip count density (null if area unknown)
             */
            chip_density_per_m2?: number | null;
            /**
             * Min Chip Diameter Mm
             * @description Minimum resolvable chip diameter (null if uncalibrated)
             */
            min_chip_diameter_mm?: number | null;
            /**
             * Median Chip Diameter Mm
             * @description Median chip diameter (null if uncalibrated)
             */
            median_chip_diameter_mm?: number | null;
            /**
             * Chip Size Distribution
             * @description Size distribution buckets
             */
            chip_size_distribution?: {
                [key: string]: number;
            } | null;
            /**
             * Aggregate Coverage
             * @description Aggregate union coverage ratio (null if unmeasured)
             */
            aggregate_coverage?: number | null;
            /**
             * Crack Skeleton Length M
             * @description Crack skeleton length (null if unmeasured/uncalibrated)
             */
            crack_skeleton_length_m?: number | null;
            /**
             * Pothole Count
             * @description Pothole instance count (null if unmeasured)
             */
            pothole_count?: number | null;
            /**
             * Pothole Total Area M2
             * @description Total pothole area (null if uncalibrated)
             */
            pothole_total_area_m2?: number | null;
            /**
             * Crack Total Area M2
             * @description Total crack area (null if uncalibrated)
             */
            crack_total_area_m2?: number | null;
            /**
             * Gap Median Mm
             * @description Adjacent-boundary gap median (null if uncalibrated)
             */
            gap_median_mm?: number | null;
            /**
             * Gap Iqr Mm
             * @description Gap interquartile range (null if uncalibrated)
             */
            gap_iqr_mm?: number | null;
            /**
             * Gap P90 Mm
             * @description Gap 90th percentile (null if uncalibrated)
             */
            gap_p90_mm?: number | null;
            /**
             * Gap Sample Count
             * @description Number of qualifying gap sites measured
             */
            gap_sample_count?: number | null;
            /**
             * Texture Deviation
             * @description Texture deviation T from known-good reference
             */
            texture_deviation?: number | null;
        };
        /**
         * AreaResult
         * @description Road area measurements.
         */
        AreaResult: {
            /**
             * Observed Area M2
             * @description Total observed road area (null if scale unknown)
             */
            observed_area_m2?: number | null;
            /**
             * Eligible Area M2
             * @description Texture-eligible area (null if scale unknown)
             */
            eligible_area_m2?: number | null;
            /**
             * Ignored Area M2
             * @description Ignored area (null if scale unknown)
             */
            ignored_area_m2?: number | null;
            /**
             * Distress Area M2
             * @description Distress area (null if scale unknown)
             */
            distress_area_m2?: number | null;
            /**
             * Scale Source
             * @description Scale source: rig_calibrated, source_calibrated, unscaled
             */
            scale_source?: string | null;
            /**
             * Scale Uncertainty
             * @description Relative scale uncertainty ratio (null if unknown)
             */
            scale_uncertainty?: number | null;
        };
        /**
         * CanonicalSampleRecord
         * @description The canonical assessment record defined in Final Plan Section 11.5.
         */
        CanonicalSampleRecord: {
            identity: components["schemas"]["SampleIdentity"];
            provenance: components["schemas"]["SampleProvenance"];
            time: components["schemas"]["SampleTime"];
            camera: components["schemas"]["SampleCamera"];
            location: components["schemas"]["SampleLocation"];
            geometry: components["schemas"]["SampleGeometry"];
            quality: components["schemas"]["QualityResult"];
            /** Features */
            features?: components["schemas"]["MetricResult"][];
            assessment: components["schemas"]["ScoreResult"];
            coverage: components["schemas"]["SampleCoverage"];
            audit: components["schemas"]["SampleAudit"];
            narrative: components["schemas"]["SampleNarrative"];
        };
        /**
         * DistressEvidence
         * @description Distress segmentation evidence.
         */
        DistressEvidence: {
            /**
             * Mask Url
             * @description URL to defect mask overlay
             */
            mask_url?: string | null;
            /**
             * Mask Local Path
             * @description Local disk path to mask overlay
             */
            mask_local_path?: string | null;
            /**
             * Crack Mask Url
             * @description URL to crack-specific mask
             */
            crack_mask_url?: string | null;
            /**
             * Pothole Mask Url
             * @description URL to pothole-specific mask
             */
            pothole_mask_url?: string | null;
            /**
             * Overlay Url
             * @description URL to combined evidence overlay
             */
            overlay_url?: string | null;
        };
        /**
         * FinalizeRequest
         * @description Request to finalize an upload and enqueue analysis.
         */
        FinalizeRequest: {
            /** @description Frame metadata (GPS, IMU, grade, capture time) */
            metadata?: components["schemas"]["FrameMetadata"] | null;
            /**
             * @description Source mode for this upload
             * @default upload
             */
            source_mode: components["schemas"]["SourceMode"];
        };
        /**
         * FinalizeResponse
         * @description Response returned after finalizing an upload.
         */
        FinalizeResponse: {
            /**
             * Upload Id
             * @description Upload identifier
             */
            upload_id: string;
            /**
             * Status
             * @description Processing status: queued
             * @default queued
             */
            status: string;
            /**
             * Job Id
             * @description Associated job ID for polling lifecycle
             */
            job_id?: string | null;
            /**
             * Message
             * @description Human-readable status message
             */
            message?: string | null;
        };
        /**
         * FrameMetadata
         * @description Metadata for a single frame.
         */
        FrameMetadata: {
            /** @description GPS fix if available */
            gps?: components["schemas"]["GPSData"] | null;
            /** @description IMU orientation data */
            imu?: components["schemas"]["IMUData"];
            /** @description Supporting road grade measurement */
            grade?: components["schemas"]["GradeMeasurement"] | null;
            /**
             * Captured At
             * @description ISO 8601 capture timestamp (UTC)
             */
            captured_at?: string | null;
            /**
             * Monotonic Capture Time Ns
             * @description Monotonic clock timestamp in nanoseconds
             */
            monotonic_capture_time_ns?: number | null;
            /**
             * Device Id
             * @description Camera or device identifier
             */
            device_id?: string | null;
            /**
             * Camera Profile Id
             * @description Camera calibration profile identifier
             */
            camera_profile_id?: string | null;
            /**
             * @description How this frame was acquired
             * @default upload
             */
            source_mode: components["schemas"]["SourceMode"];
            /**
             * Frame Index
             * @description Sequence number for live or replay
             */
            frame_index?: number | null;
            /**
             * Telemetry Hash
             * @description SHA256 hash of raw telemetry payload
             */
            telemetry_hash?: string | null;
        };
        /**
         * GPSData
         * @description GPS fix attached to a frame.
         */
        GPSData: {
            /**
             * Lat
             * @description Latitude in degrees
             */
            lat: number;
            /**
             * Lon
             * @description Longitude in degrees
             */
            lon: number;
            /**
             * Speed Mps
             * @description Speed in meters per second (null if unknown)
             */
            speed_mps?: number | null;
            /**
             * Heading Deg
             * @description Heading in degrees (null if unknown)
             */
            heading_deg?: number | null;
            /**
             * Accuracy M
             * @description Horizontal accuracy in meters (null if unknown)
             */
            accuracy_m?: number | null;
            /**
             * Simulated
             * @description True if GPS is simulated, not real hardware GPS
             * @default false
             */
            simulated: boolean;
        };
        /**
         * GradeMeasurement
         * @description Verified road inclination / grade measurement.
         */
        GradeMeasurement: {
            /**
             * Grade Percent
             * @description Longitudinal road grade in percent: 100 * tan(angle). Null if unmeasured.
             */
            grade_percent?: number | null;
            /**
             * Grade Deg
             * @description Longitudinal grade in degrees. Null if unmeasured.
             */
            grade_deg?: number | null;
            /**
             * Source
             * @description Source provenance: manual_sensor, calibrated_inclinometer, stationary_camera_imu
             */
            source: string;
            /**
             * Uncertainty Deg
             * @description Estimated uncertainty in degrees (null if unknown)
             */
            uncertainty_deg?: number | null;
            /**
             * Captured At
             * @description ISO 8601 capture timestamp of the sensor measurement
             */
            captured_at?: string | null;
            /**
             * Valid
             * @description Whether this grade reading is considered valid under current mounting
             * @default true
             */
            valid: boolean;
            /**
             * Notes
             * @description Clarifications: e.g. longitudinal vs crossfall, straightedge verification
             */
            notes?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthStatus
         * @description Basic service health status.
         */
        HealthStatus: {
            /**
             * Status
             * @description Overall service status: healthy, degraded, unhealthy
             * @default healthy
             */
            status: string;
            /**
             * Version
             * @description API version
             */
            version: string;
            /**
             * Services
             * @description Sub-service statuses: database, s3, bedrock, model, worker
             */
            services?: {
                [key: string]: unknown;
            };
        };
        /**
         * IMUData
         * @description Device orientation captured with the frame.
         */
        IMUData: {
            /**
             * Pitch Deg
             * @description Pitch in degrees
             * @default 0
             */
            pitch_deg: number;
            /**
             * Roll Deg
             * @description Roll in degrees
             * @default 0
             */
            roll_deg: number;
            /**
             * Yaw Deg
             * @description Yaw in degrees (null if unknown)
             */
            yaw_deg?: number | null;
            /**
             * Accel Z
             * @description Vertical acceleration (null if unknown)
             */
            accel_z?: number | null;
        };
        /**
         * JobState
         * @description Durable job lifecycle state.
         */
        JobState: {
            /**
             * Job Id
             * @description Unique job identifier
             */
            job_id: string;
            /** @description Current job status: received -> validated -> queued -> processing -> succeeded/partial/failed */
            status: components["schemas"]["JobStatus"];
            /**
             * Error Reason
             * @description Error description if failed
             */
            error_reason?: string | null;
            /**
             * Attempt Count
             * @description Number of processing attempts
             * @default 0
             */
            attempt_count: number;
            /**
             * Started At
             * @description When processing began
             */
            started_at?: string | null;
            /**
             * Completed At
             * @description When processing ended
             */
            completed_at?: string | null;
            /**
             * Updated At
             * @description Last state transition timestamp
             */
            updated_at: string;
            /**
             * Versions
             * @description Model, feature, and scoring versions used
             */
            versions?: {
                [key: string]: string;
            };
            /**
             * Result Sample Id
             * @description Sample id produced when the job succeeded (null until then). Retrieve via GET /v1/samples/{id}.
             */
            result_sample_id?: string | null;
        };
        /**
         * JobStatus
         * @description Analysis job lifecycle states.
         * @enum {string}
         */
        JobStatus: "received" | "validated" | "queued" | "processing" | "succeeded" | "partial" | "failed";
        /**
         * MetricResult
         * @description Single measured metric with validity information.
         */
        MetricResult: {
            /**
             * Name
             * @description Metric identifier, e.g. chip_count_density, median_chip_diameter
             */
            name: string;
            /**
             * Value
             * @description Measured value (null = unknown, 0 = measured absence)
             */
            value?: number | null;
            /**
             * Unit
             * @description Unit of measurement: mm, m2, count/m2, unitless
             */
            unit: string;
            /**
             * Valid
             * @description Whether the measurement is valid
             * @default true
             */
            valid: boolean;
            /**
             * Estimator Version
             * @description Version of estimator that produced this
             */
            estimator_version?: string | null;
            /**
             * Notes
             * @description Human-readable notes about this metric
             */
            notes?: string | null;
        };
        /**
         * NarrativeStatus
         * @description Bedrock narrative generation status.
         * @enum {string}
         */
        NarrativeStatus: "generated" | "fallback" | "not_requested";
        /**
         * QualityResult
         * @description Image quality assessment.
         */
        QualityResult: {
            /** @description Overall quality status: accepted, limited, rejected */
            status: components["schemas"]["QualityStatus"];
            /**
             * Reasons
             * @description Reason codes: e.g. blur_laplacian, glare, uncalibrated_scale
             */
            reasons?: string[];
            /**
             * Min Source Resolution
             * @description Minimum detectable feature size in pixels
             */
            min_source_resolution?: number | null;
            /**
             * Sharpness Score
             * @description Sharpness metric value (null if uncomputed)
             */
            sharpness_score?: number | null;
            /**
             * Glare Present
             * @description Whether glare or clipping was detected
             * @default false
             */
            glare_present: boolean;
            /**
             * Ignored Fraction
             * @description Fraction of frame masked as ignore
             */
            ignored_fraction?: number | null;
        };
        /**
         * QualityStatus
         * @description Image quality assessment status.
         * @enum {string}
         */
        QualityStatus: "accepted" | "limited" | "rejected";
        /**
         * ReferenceComparison
         * @description Comparison against known-good reference.
         */
        ReferenceComparison: {
            /**
             * Reference Version
             * @description Version of the reference model used
             */
            reference_version?: string | null;
            /**
             * Feature Count
             * @description Number of features compared
             */
            feature_count?: number | null;
            /**
             * Deviation Robust
             * @description Robust normalized deviation (null if uncomputed)
             */
            deviation_robust?: number | null;
            /**
             * Deviation Mahalanobis
             * @description Mahalanobis distance (null if uncomputed)
             */
            deviation_mahalanobis?: number | null;
            /**
             * Supported Surface
             * @description Whether the surface is in the supported domain
             * @default true
             */
            supported_surface: boolean;
            /**
             * Domain Support Covered
             * @description Whether domain support was explicitly checked
             * @default false
             */
            domain_support_covered: boolean;
            /**
             * Difference Heatmap Url
             * @description URL to difference heatmap (null if uncomputed)
             */
            difference_heatmap_url?: string | null;
        };
        /**
         * ReportContent
         * @description Structured report content containing verified facts and inspection actions.
         */
        ReportContent: {
            /**
             * Summary
             * @description Human-readable factual summary
             */
            summary: string;
            /**
             * Evidence References
             * @description References to evidence items (sample IDs, masks)
             */
            evidence_references?: string[];
            /**
             * Limitations
             * @description Declared limitations (e.g. uncalibrated scale, partial route)
             */
            limitations?: string[];
            /**
             * Inspection Actions
             * @description Recommended human inspection actions (never structural repair commands)
             */
            inspection_actions?: string[];
            /**
             * @description How narrative was produced: generated, fallback, not_requested
             * @default not_requested
             */
            narrative_status: components["schemas"]["NarrativeStatus"];
            /**
             * Factual Template Used
             * @description True if deterministic fallback template was used
             * @default false
             */
            factual_template_used: boolean;
        };
        /**
         * ReportResult
         * @description Generated factual report with Bedrock narration metadata.
         */
        ReportResult: {
            /**
             * Report Id
             * @description Unique report identifier
             */
            report_id: string;
            /**
             * Assessment Id
             * @description Assessment or session ID this report covers
             */
            assessment_id?: string | null;
            /** @description Structured report content */
            content: components["schemas"]["ReportContent"];
            /**
             * Generated At
             * @description UTC generation timestamp
             */
            generated_at: string;
            /**
             * Bedrock Model Id
             * @description Exact AWS Bedrock model ID used (null if fallback/none)
             */
            bedrock_model_id?: string | null;
            /**
             * Factual Input Hash
             * @description SHA256 hash of structured facts used for caching and validation
             */
            factual_input_hash?: string | null;
        };
        /** SampleAudit */
        SampleAudit: {
            /**
             * Model Hash
             * @description Hash of ML model weights
             */
            model_hash?: string | null;
            /**
             * Code Commit
             * @description Git commit hash of running service
             */
            code_commit?: string | null;
            /**
             * Config Hash
             * @description Hash of active configuration
             */
            config_hash?: string | null;
            /**
             * Reviewer Corrections
             * @description Human reviewer audit annotations
             */
            reviewer_corrections?: {
                [key: string]: unknown;
            } | null;
        };
        /** SampleCamera */
        SampleCamera: {
            /**
             * Camera Id
             * @description Camera hardware ID
             */
            camera_id?: string | null;
            /**
             * Calibration Id
             * @description Calibration profile ID
             */
            calibration_id?: string | null;
            /**
             * Width Px
             * @description Native frame width in pixels
             */
            width_px?: number | null;
            /**
             * Height Px
             * @description Native frame height in pixels
             */
            height_px?: number | null;
            /**
             * Exposure Ms
             * @description Exposure duration in milliseconds
             */
            exposure_ms?: number | null;
            /**
             * Crop State
             * @description Crop or digital zoom description
             */
            crop_state?: string | null;
        };
        /** SampleCoverage */
        SampleCoverage: {
            /**
             * Frame Interval M
             * @description Distance spacing between consecutive frames
             */
            frame_interval_m?: number | null;
            /**
             * Inspected Strip M
             * @description Transverse width of inspected pavement strip
             */
            inspected_strip_m?: number | null;
            /**
             * Unique Area M2
             * @description Unique pavement area (null if registration unreliable)
             */
            unique_area_m2?: number | null;
            /**
             * Coverage Method
             * @description Method used to estimate coverage
             * @default conservative_spacing
             */
            coverage_method: string;
        };
        /** SampleGeometry */
        SampleGeometry: {
            /**
             * Scale Source
             * @description Scale determination: rig_calibrated, source_calibrated, unscaled
             */
            scale_source: string;
            /**
             * Sx Sy Or H
             * @description x/y scale factors (mm/px) or 3x3 homography matrix H
             */
            sx_sy_or_h?: number[] | null;
            /**
             * Valid Roi
             * @description Bounding box [x, y, w, h] of valid road ROI
             */
            valid_roi?: number[] | null;
            /**
             * Observed Area M2
             * @description Total valid area inspected (null if uncalibrated)
             */
            observed_area_m2?: number | null;
            /**
             * Error Bound Pct
             * @description Scale error bound percentage
             */
            error_bound_pct?: number | null;
        };
        /** SampleIdentity */
        SampleIdentity: {
            /**
             * Sample Id
             * @description Unique sample ID
             */
            sample_id: string;
            /**
             * Session Id
             * @description Parent session ID
             */
            session_id?: string | null;
            /**
             * Source Dataset
             * @description Dataset name and version if from benchmark
             */
            source_dataset?: string | null;
            /**
             * Parent Id
             * @description Parent image ID
             */
            parent_id?: string | null;
            /**
             * Sequence Id
             * @description Sequence index in route
             */
            sequence_id?: number | null;
        };
        /** SampleLocation */
        SampleLocation: {
            /**
             * Lat
             * @description Latitude (null if unlocated)
             */
            lat?: number | null;
            /**
             * Lon
             * @description Longitude (null if unlocated)
             */
            lon?: number | null;
            /**
             * Accuracy M
             * @description GPS accuracy radius in meters
             */
            accuracy_m?: number | null;
            /**
             * Route Distance M
             * @description Traveled distance along route
             */
            route_distance_m?: number | null;
            /**
             * Distance Source
             * @description Source of route distance: odometry, gps_polyline
             */
            distance_source?: string | null;
            /**
             * Is Simulated
             * @description True if simulated GPS coordinates
             * @default false
             */
            is_simulated: boolean;
        };
        /** SampleNarrative */
        SampleNarrative: {
            /**
             * Factual Input Hash
             * @description SHA256 hash of structured facts sent to Bedrock
             */
            factual_input_hash?: string | null;
            /**
             * Bedrock Model Id
             * @description Exact AWS Bedrock model ID used
             */
            bedrock_model_id?: string | null;
            /**
             * @description Narrative status
             * @default not_requested
             */
            status: components["schemas"]["NarrativeStatus"];
            /**
             * Generated At
             * @description UTC generation timestamp
             */
            generated_at?: string | null;
        };
        /** SampleProvenance */
        SampleProvenance: {
            /**
             * File Sha256
             * @description SHA256 hash of original image file
             */
            file_sha256: string;
            /**
             * Original Uri
             * @description Original URI or S3 object key
             */
            original_uri: string;
            /**
             * License Record
             * @description License terms or attribution
             */
            license_record?: string | null;
            /**
             * Split Group
             * @description Evaluation split group (train, dev, test)
             */
            split_group?: string | null;
        };
        /** SampleTime */
        SampleTime: {
            /**
             * Captured At Utc
             * @description UTC capture timestamp (ISO 8601)
             */
            captured_at_utc?: string | null;
            /**
             * Monotonic Capture Time Ns
             * @description Monotonic clock reading in nanoseconds
             */
            monotonic_capture_time_ns?: number | null;
            /**
             * Received At
             * @description UTC timestamp when server received the frame
             */
            received_at: string;
            /**
             * Processed At
             * @description UTC timestamp when analysis completed
             */
            processed_at?: string | null;
        };
        /**
         * ScoreResult
         * @description Surface Quality Index (SQI) score.
         */
        ScoreResult: {
            /**
             * Value
             * @description SQI value 0-100 (null = not scored/unknown)
             */
            value?: number | null;
            /**
             * @description Good, Bad, review, unknown
             * @default unknown
             */
            status: components["schemas"]["ScoreStatus"];
            /**
             * Reference Version
             * @description Version of reference used for scoring
             */
            reference_version?: string | null;
            /**
             * Policy Version
             * @description Version of scoring policy used
             */
            policy_version?: string | null;
            /**
             * Texture Term
             * @description Texture deviation component T
             */
            texture_term?: number | null;
            /**
             * Distress Term
             * @description Distress burden component D
             */
            distress_term?: number | null;
            /**
             * Distribution Term
             * @description Optional distribution term
             */
            distribution_term?: number | null;
            /**
             * Confidence
             * @description Empirically calibrated confidence
             */
            confidence?: number | null;
            /**
             * Confidence State
             * @description Descriptive confidence state: high, medium, low, uncalibrated
             */
            confidence_state?: string | null;
            /**
             * Severe Defect Flag
             * @description Inspection priority flag for severe observed defect
             * @default false
             */
            severe_defect_flag: boolean;
            /**
             * Reasons
             * @description Scoring reason codes
             */
            reasons?: string[];
            /**
             * Partial Rule
             * @description Name of partial-input rule if applied
             */
            partial_rule?: string | null;
        };
        /**
         * ScoreStatus
         * @description Surface condition scoring status.
         * @enum {string}
         */
        ScoreStatus: "Good" | "Bad" | "review" | "unknown";
        /**
         * SegmentList
         * @description List of segment summaries for a route.
         */
        SegmentList: {
            /**
             * Route Id
             * @description Route or session identifier
             */
            route_id: string;
            /**
             * Segments
             * @description Reporting bin summaries
             */
            segments?: components["schemas"]["SegmentSummary"][];
            /**
             * Total Distance M
             * @description Total route distance in meters
             * @default 0
             */
            total_distance_m: number;
            /**
             * Coverage Percentage
             * @description Percentage of route covered (null if unknown)
             */
            coverage_percentage?: number | null;
            /**
             * Unsampled Stretches
             * @description Unsampled distance ranges [{'start_m': ..., 'end_m': ...}]
             */
            unsampled_stretches?: {
                [key: string]: number;
            }[];
        };
        /**
         * SegmentResult
         * @description Full analysis result for one route segment or uploaded frame.
         */
        SegmentResult: {
            /**
             * Segment Id
             * @description Segment identifier (1-based sequence or index)
             */
            segment_id: number;
            /**
             * Route Id
             * @description Parent route or session identifier
             */
            route_id?: string | null;
            /**
             * Sample Id
             * @description Unique sample identifier
             */
            sample_id?: string | null;
            /**
             * Image Path
             * @description Path to original image
             */
            image_path?: string | null;
            /**
             * Image Url
             * @description URL to original image
             */
            image_url?: string | null;
            /**
             * Mask Url
             * @description URL to mask overlay
             */
            mask_url?: string | null;
            /**
             * Raw Url
             * @description URL to raw uploaded image
             */
            raw_url?: string | null;
            /**
             * Captured At
             * @description UTC capture timestamp
             */
            captured_at?: string | null;
            /** @description GPS fix if available */
            gps?: components["schemas"]["GPSData"] | null;
            /** @description Supporting road grade measurement */
            grade?: components["schemas"]["GradeMeasurement"] | null;
            /**
             * Geometry Valid
             * @description Whether geometry and scale are valid
             * @default false
             */
            geometry_valid: boolean;
            /** @description Area measurements (null if uncalibrated) */
            observed_area?: components["schemas"]["AreaResult"] | null;
            /** @description Quality assessment */
            quality?: components["schemas"]["QualityResult"] | null;
            /** @description Aggregate and distress metrics */
            metrics?: components["schemas"]["AggregatedMetrics"] | null;
            /** @description Visual evidence references */
            evidence?: components["schemas"]["DistressEvidence"] | null;
            /** @description Surface condition score */
            score?: components["schemas"]["ScoreResult"] | null;
            /** @description Known-good comparison */
            reference?: components["schemas"]["ReferenceComparison"] | null;
            /**
             * Model Version
             * @description ML model version used
             */
            model_version?: string | null;
            /**
             * Feature Version
             * @description Feature extraction version
             */
            feature_version?: string | null;
            /**
             * Scoring Version
             * @description Scoring version
             */
            scoring_version?: string | null;
            /**
             * Created At
             * @description Analysis completion timestamp
             */
            created_at?: string | null;
            /**
             * Error
             * @description Error message if analysis failed
             */
            error?: string | null;
            /** @description Canonical record if available */
            canonical?: components["schemas"]["CanonicalSampleRecord"] | null;
        };
        /**
         * SegmentSummary
         * @description Summary for a configurable 50m reporting bin.
         */
        SegmentSummary: {
            /**
             * Segment Id
             * @description Reporting bin sequence identifier
             */
            segment_id: number;
            /**
             * Start Distance M
             * @description Start distance along route in meters
             */
            start_distance_m: number;
            /**
             * End Distance M
             * @description End distance along route in meters
             */
            end_distance_m: number;
            /**
             * Center Lat
             * @description Center GPS latitude (null if unlocated)
             */
            center_lat?: number | null;
            /**
             * Center Lon
             * @description Center GPS longitude (null if unlocated)
             */
            center_lon?: number | null;
            /**
             * Gps Accuracy M
             * @description GPS accuracy at center (null if unknown)
             */
            gps_accuracy_m?: number | null;
            /**
             * Simulated
             * @description Whether position is simulated
             * @default false
             */
            simulated: boolean;
            /**
             * Sample Count
             * @description Number of frames received in this bin
             * @default 0
             */
            sample_count: number;
            /**
             * Accepted Sample Count
             * @description Frames that passed QC checks
             * @default 0
             */
            accepted_sample_count: number;
            /**
             * Unique Area M2
             * @description Unique road area covered (null if registration unreliable)
             */
            unique_area_m2?: number | null;
            /**
             * Strip Area M2
             * @description Total inspected strip area sampled
             * @default 0
             */
            strip_area_m2: number;
            /**
             * Median Score
             * @description Median SQI (null if not enough samples)
             */
            median_score?: number | null;
            /**
             * Lower Tail Score
             * @description Lower-tail SQI (p10/p25) (null if insufficient samples)
             */
            lower_tail_score?: number | null;
            /**
             * Serious Defect Observed
             * @description Whether a severe defect flag was observed in this bin
             * @default false
             */
            serious_defect_observed: boolean;
            /**
             * Unknown Coverage
             * @description Whether coverage is incomplete or unsampled
             * @default false
             */
            unknown_coverage: boolean;
        };
        /**
         * SessionState
         * @description Live/replay capture session state.
         */
        SessionState: {
            /**
             * Session Id
             * @description Unique session identifier
             */
            session_id: string;
            /** @description Capture mode: live, replay, upload */
            mode: components["schemas"]["SourceMode"];
            /**
             * Camera Id
             * @description Camera hardware ID
             */
            camera_id?: string | null;
            /**
             * Calibration Id
             * @description Calibration profile ID
             */
            calibration_id?: string | null;
            /**
             * Created At
             * @description Session creation timestamp
             */
            created_at: string;
            /**
             * Frame Count
             * @description Frames received by API
             * @default 0
             */
            frame_count: number;
            /**
             * Processed Count
             * @description Frames processed by worker
             * @default 0
             */
            processed_count: number;
            /**
             * Rejected Count
             * @description Frames rejected by QC or format validation
             * @default 0
             */
            rejected_count: number;
            /**
             * Dropped Count
             * @description Frames dropped due to bounded queue overflow
             * @default 0
             */
            dropped_count: number;
            /**
             * Last Capture At
             * @description Last frame capture timestamp
             */
            last_capture_at?: string | null;
            /**
             * Last Processed At
             * @description Last frame processed timestamp
             */
            last_processed_at?: string | null;
            /**
             * Is Stale
             * @description Whether current result is stale
             * @default false
             */
            is_stale: boolean;
        };
        /**
         * SourceMode
         * @description How the image was acquired.
         * @enum {string}
         */
        SourceMode: "upload" | "live" | "replay";
        /**
         * UploadRequest
         * @description Request to allocate a private upload slot.
         */
        UploadRequest: {
            /**
             * Filename
             * @description Original filename
             */
            filename: string;
            /**
             * Content Type
             * @description MIME type (e.g. image/jpeg, image/png)
             */
            content_type?: string | null;
            /**
             * Expected Size
             * @description Expected file size in bytes (max 50MB)
             */
            expected_size?: number | null;
        };
        /**
         * UploadResponse
         * @description Response returned when an upload slot is allocated.
         */
        UploadResponse: {
            /**
             * Upload Id
             * @description Unique upload identifier
             */
            upload_id: string;
            /**
             * Upload Url
             * @description Presigned S3 upload URL or local upload endpoint
             */
            upload_url: string;
            /**
             * Object Key
             * @description Private object key path
             */
            object_key: string;
            /**
             * Expires At
             * @description Upload URL expiration timestamp (ISO 8601)
             */
            expires_at?: string | null;
            /**
             * Status
             * @description Upload slot status
             * @default ready
             */
            status: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    create_upload_v1_uploads_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UploadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_local_v1_uploads__upload_id__local_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    finalize_upload_v1_uploads__upload_id__finalize_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["FinalizeRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinalizeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_session_v1_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ingest_frame_v1_sessions__session_id__frames_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    finish_session_v1_sessions__session_id__finish_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_job_v1_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_sample_v1_samples__sample_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sample_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_session_segments_v1_sessions__session_id__segments_get: {
        parameters: {
            query?: {
                bin_length_m?: number;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentList"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_report_v1_reports_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    v1_health_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthStatus"];
                };
            };
        };
    };
    health_liveness_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    health_deep_health_deep_get: {
        parameters: {
            query?: {
                /** @description auto = cached AWS probes, aws = force fresh probes, none = configuration only */
                probe?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    root_health__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
