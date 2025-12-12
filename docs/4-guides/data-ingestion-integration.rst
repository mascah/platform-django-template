Data Ingestion and Integration Patterns
=======================================

Patterns for ingesting external data into your modular monolith: bulk imports from S3 and SFTP, real-time webhooks, FHIR healthcare integrations, and external API polling.

Overview
--------

Data ingestion typically falls into two categories based on volume and latency requirements:

**Bulk ingestion** handles large datasets delivered infrequently. Customers upload CSV files to S3 or SFTP, and background workers process them over minutes or hours. This pattern suits initial data migrations, nightly batch syncs, and large file uploads.

**Real-time ingestion** handles continuous data streams with low latency. External systems push data via webhooks, or your application polls APIs for changes. This pattern suits event-driven integrations, FHIR healthcare data, and near real-time synchronization.

+------------------------+-------------------+---------------------------+
| Aspect                 | Bulk Ingestion    | Real-Time Ingestion       |
+========================+===================+===========================+
| Data volume            | Large (MB to GB)  | Small (individual records)|
+------------------------+-------------------+---------------------------+
| Frequency              | Infrequent        | Continuous                |
+------------------------+-------------------+---------------------------+
| Latency tolerance      | Minutes to hours  | Seconds to minutes        |
+------------------------+-------------------+---------------------------+
| Trigger                | File arrival      | Webhook or poll           |
+------------------------+-------------------+---------------------------+
| Processing             | Batched           | Individual                |
+------------------------+-------------------+---------------------------+

Both patterns share common concerns: idempotency, error handling, progress tracking, and integration with your domain model through the service layer.

Bulk Data Ingestion
-------------------

Bulk ingestion requires tracking import state across long-running operations. An import job model provides visibility into progress, enables resumability after failures, and creates an audit trail.

Import Job Model
^^^^^^^^^^^^^^^^

The core of bulk ingestion is a model that tracks each import operation:

.. code-block:: python

    # {project_slug}/integrations/models.py
    class ImportJobStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        PARTIALLY_COMPLETED = "partially_completed", "Partially Completed"


    class ImportJob(models.Model):
        """Tracks the state of a data import operation."""

        uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
        source_type = models.CharField(max_length=50)  # "s3", "sftp", "webhook"
        source_identifier = models.CharField(max_length=500)  # S3 URI, SFTP path

        status = models.CharField(max_length=20, choices=ImportJobStatus.choices)

        # Progress tracking
        total_records = models.IntegerField(null=True, blank=True)
        processed_records = models.IntegerField(default=0)
        successful_records = models.IntegerField(default=0)
        failed_records = models.IntegerField(default=0)

        # Resumability - track where processing left off
        last_processed_offset = models.IntegerField(default=0)

        # Timing and errors
        started_at = models.DateTimeField(null=True, blank=True)
        completed_at = models.DateTimeField(null=True, blank=True)
        error_message = models.TextField(blank=True)
        metadata = models.JSONField(default=dict)

Key fields:

- ``source_identifier`` — The S3 URI or SFTP path, used for idempotency checks
- ``last_processed_offset`` — Enables resuming failed imports from where they stopped
- ``metadata`` — Stores source-specific details (bucket, key, file size)

Create a related ``ImportJobError`` model to capture row-level failures with row number, error type, and the raw data that failed validation.

S3 File Processing
^^^^^^^^^^^^^^^^^^

Two approaches exist for detecting new files in S3:

**Polling** — A Celery Beat task periodically lists an S3 bucket. For each new file, check if an ``ImportJob`` already exists for that S3 URI (idempotency), create a job record, and queue processing. Schedule via ``CELERY_BEAT_SCHEDULE`` to run every 5-15 minutes.

**Event-driven** — Configure S3 bucket notifications to publish to SNS, subscribe an SQS queue, and consume events with a Celery task. This provides near-instant processing when files arrive. The event payload contains the bucket and key; apply the same idempotency check before creating an ``ImportJob``.

The processing task follows this pattern:

1. Check idempotency (skip if already completed)
2. Update status to ``IN_PROGRESS``
3. Download and process the file
4. Update status to ``COMPLETED`` or ``PARTIALLY_COMPLETED``
5. Move processed file to an archive prefix

Use ``boto3`` for S3 access. Handle ``ClientError`` with retries using exponential backoff.

SFTP Polling
^^^^^^^^^^^^

For SFTP sources, a Celery Beat task periodically connects via ``paramiko``:

1. List files in the incoming directory
2. For each CSV file, check if already processed (idempotency via ``source_identifier``)
3. Download to a temp location
4. Create ``ImportJob`` and queue processing
5. Move the file to a processed directory on the SFTP server

Store SFTP credentials (host, port, username, password) in environment variables.

Chunked CSV Processing
^^^^^^^^^^^^^^^^^^^^^^

Process large CSV files in batches to manage memory and provide progress updates:

.. code-block:: python

    # {project_slug}/integrations/services.py
    BATCH_SIZE = 1000

    def process_csv_stream(job: ImportJob, stream) -> None:
        """Process CSV in batches with progress tracking."""
        reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
        batch = []

        for row_number, row in enumerate(reader, 1):
            # Resumability - skip already processed rows
            if row_number <= job.last_processed_offset:
                continue

            try:
                batch.append(validate_row(row))
            except ValidationError as e:
                record_row_error(job, row_number, str(e), row)
                job.failed_records += 1

            if len(batch) >= BATCH_SIZE:
                process_batch(job, batch)
                batch = []
                # Update progress for visibility and resumability
                job.processed_records = row_number
                job.last_processed_offset = row_number
                job.save(update_fields=["processed_records", "last_processed_offset"])

        if batch:
            process_batch(job, batch)

The ``last_processed_offset`` field enables resumability. If processing fails mid-way, restarting the task skips rows that were already handled.

Error Handling and Recovery
^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Idempotent imports** — Use hash-based deduplication to prevent duplicates when re-running imports. Compute a SHA-256 hash of key fields (e.g., email, external_id) and store it on the imported record. Check for existing hashes before inserting.

**Resumable imports** — The ``last_processed_offset`` tracks progress. To resume a failed import, reset status to ``PENDING`` and requeue the task—processing will skip to the last offset.

**Partial success** — Use ``PARTIALLY_COMPLETED`` status when some rows succeed and others fail. Store failed rows in ``ImportJobError`` with the raw data for debugging and manual correction.

Near Real-Time Ingestion
------------------------

Real-time ingestion handles individual records as they arrive. The key pattern: acknowledge receipt immediately, then process asynchronously.

Webhook Endpoints
^^^^^^^^^^^^^^^^^

The critical pattern for webhooks is immediate acknowledgment with async processing:

.. code-block:: python

    # {project_slug}/integrations/api/views.py
    class WebhookView(APIView):
        authentication_classes = []  # Webhooks use signature verification
        permission_classes = []

        def post(self, request, source: str):
            # 1. Verify HMAC signature
            if not self._verify_signature(request, source):
                return Response(status=status.HTTP_401_UNAUTHORIZED)

            # 2. Extract idempotency key from payload or headers
            payload_id = request.data.get("id") or request.headers.get("X-Webhook-ID")

            # 3. Skip if already processed (idempotency)
            if WebhookDelivery.objects.filter(source=source, external_id=payload_id).exists():
                return Response({"status": "already_processed"})

            # 4. Record delivery immediately
            delivery = WebhookDelivery.objects.create(
                source=source,
                external_id=payload_id,
                payload=request.data,
            )

            # 5. Queue async processing - only after transaction commits
            process_webhook_payload.delay_on_commit(delivery.id)

            # 6. Acknowledge immediately
            return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)

Create a ``WebhookDelivery`` model with ``source``, ``external_id`` (unique together for idempotency), ``payload``, ``status``, and timestamps.

For signature verification, use HMAC-SHA256 with a per-source secret stored in settings. Compare the computed signature against the ``X-Signature-256`` header using ``hmac.compare_digest`` for timing-safe comparison.

FHIR Integration Patterns
^^^^^^^^^^^^^^^^^^^^^^^^^

FHIR (Fast Healthcare Interoperability Resources) is the standard for healthcare data exchange.

**Resource mapping** — FHIR resources have complex nested structures. Create mapper functions that extract the fields you need into simple dataclasses:

.. code-block:: python

    # {project_slug}/integrations/fhir/mappers.py
    @dataclass
    class MappedPatient:
        fhir_id: str
        mrn: str
        first_name: str
        last_name: str
        birth_date: str

    def map_fhir_patient(resource: dict) -> MappedPatient:
        """Map FHIR Patient resource to domain representation."""
        # Extract identifiers, names, telecom from nested FHIR structure
        # Return clean dataclass for your domain layer

Create a registry of mappers by resource type (``Patient``, ``Observation``, etc.) to process FHIR Bundles containing multiple resources.

**FHIR Subscriptions** — For real-time updates, FHIR R4/R5 servers push notification bundles when resources change. Create an endpoint that:

1. Handles ``handshake`` and ``heartbeat`` bundle types (return 200 OK)
2. For ``event-notification`` bundles, extract the ``SubscriptionStatus`` for idempotency
3. Queue async processing with ``delay_on_commit()``
4. Return 200 OK immediately

External API Polling
^^^^^^^^^^^^^^^^^^^^

For APIs without webhooks, poll periodically. Key patterns:

- **Cursor-based pagination** — Store ``last_cursor`` to resume from where you left off
- **ETag support** — Send ``If-None-Match`` header; handle 304 Not Modified efficiently
- **Rate limiting** — Use Celery's ``rate_limit`` option and respect ``Retry-After`` headers on 429 responses
- **Incremental state** — Store polling state (cursor, ETag, last_polled_at) in an ``ExternalIntegration`` model

Integration Module Structure
----------------------------

Organize integration code in a dedicated Django app:

.. code-block:: text

    {project_slug}/
    └── integrations/
        ├── models.py           # ImportJob, WebhookDelivery, ExternalIntegration
        ├── services.py         # CSV processing, deduplication logic
        ├── tasks.py            # Celery tasks for all ingestion
        ├── admin.py            # Django admin for monitoring
        ├── api/
        │   └── views.py        # WebhookView, FHIRSubscriptionView
        └── fhir/
            └── mappers.py      # FHIR resource mapping

**Domain events** — Publish ``ImportCompletedEvent`` and ``ImportFailedEvent`` after imports finish, allowing other modules to react (e.g., trigger downstream processing, send notifications). Use ``transaction.on_commit()`` as described in :doc:`event-driven-architecture`.

Django Admin Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^

Configure Django Admin for operational visibility:

- ``ImportJobAdmin`` — List display with status badge (color-coded), progress percentage, record counts. Add list filters for status and source_type. Include an inline for ``ImportJobError`` to view row-level failures. Add a "Retry failed imports" action.
- ``WebhookDeliveryAdmin`` — List by source and status, search by external_id
- ``ExternalIntegrationAdmin`` — Monitor polling state and last_polled_at

Testing Integration Code
------------------------

Test integration code by mocking external services:

- **S3 imports** — Patch ``boto3.client`` and mock ``get_object`` to return a ``BytesIO`` with CSV content
- **Webhooks** — Use DRF's ``APIClient``, compute valid HMAC signatures, verify ``WebhookDelivery`` records are created
- **Idempotency** — Verify that duplicate calls are handled correctly (return early, don't reprocess)

Production Considerations
-------------------------

**Monitoring** — Log structured events at import completion with duration, record counts, and success rate. Configure alerts for failed imports and high error rates.

**Database performance** — Use ``bulk_create`` with ``batch_size=500`` for efficient inserts. Consider ``ignore_conflicts=True`` for idempotent upserts.

**Large files** — For very large files (GB+), stream directly from S3 using ``smart_open`` rather than downloading to memory or disk.

**Recommended libraries:**

- ``boto3`` — S3 access
- ``paramiko`` — SFTP client
- ``httpx`` — HTTP client for API polling (async-friendly)
- ``smart_open`` — Streaming access to S3 files

See Also
--------

- :doc:`event-driven-architecture` — Publishing domain events after imports
- :doc:`production-patterns` — Celery ``delay_on_commit()``, idempotent task patterns
- :doc:`service-layer-patterns` — Organizing import business logic
- :doc:`adding-modules` — Creating the integrations module
- :doc:`testing` — Testing async code with pytest
- :doc:`observability-logging` — Structured logging for import tracking
