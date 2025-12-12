Model Auditing and Version History
===================================

.. index:: auditing, history, versioning, audit-log, compliance, model-tracking

Track changes to your Django models for compliance, debugging, and accountability. This guide covers two battle-tested approaches: snapshot-based history with django-simple-history and delta-based audit logs with django-auditlog.

Overview
--------

Audit trails answer critical questions: Who changed this data? When? What was the previous value? In regulated industries, audit logs are legally required. In any production system, they're invaluable for debugging and understanding data flow.

The modular monolith already provides ``BaseModel`` with ``created_at`` and ``last_modified_at`` timestamps. These tell you *when* data changed but not *what* changed or *who* changed it. Full audit logging captures this additional context.

Two approaches exist, each with distinct trade-offs:

**Snapshot-based history (django-simple-history)**: Stores a complete copy of the model on every change. Enables time-travel queries ("what did this record look like last Tuesday?") and one-click revert in the admin. Higher storage cost, but simpler queries and built-in recovery.

**Delta-based audit logs (django-auditlog)**: Stores only the changed fields as JSON. Lower storage footprint, but reconstructing historical state requires walking the change log. Better for high-volume, write-heavy systems where storage matters.

Choosing an Approach
--------------------

Use this decision matrix to select the right tool:

+------------------------+---------------------------+---------------------------+
| Consideration          | django-simple-history     | django-auditlog           |
+========================+===========================+===========================+
| Storage model          | Full row snapshots        | JSON field deltas         |
+------------------------+---------------------------+---------------------------+
| Time-travel queries    | Yes (``as_of()``)         | Manual reconstruction     |
+------------------------+---------------------------+---------------------------+
| Revert capability      | Built-in admin action     | Manual implementation     |
+------------------------+---------------------------+---------------------------+
| Storage efficiency     | Lower (full copies)       | Higher (changes only)     |
+------------------------+---------------------------+---------------------------+
| Query complexity       | Simple (standard ORM)     | Moderate (JSON parsing)   |
+------------------------+---------------------------+---------------------------+
| Admin integration      | Rich (view/revert UI)     | Basic (log display)       |
+------------------------+---------------------------+---------------------------+
| Django/Python support  | 4.2-6.0 / 3.10-3.14       | 4.2+ / 3.9+               |
+------------------------+---------------------------+---------------------------+

**Choose django-simple-history when:**

- You need point-in-time queries ("show me the order as of 3pm yesterday")
- Legal or compliance requirements mandate full historical records
- Non-technical users need to view and revert changes in the admin
- Models have relatively few writes and storage cost is acceptable

**Choose django-auditlog when:**

- You primarily need "who changed what" audit trails
- Models have frequent updates and storage efficiency matters
- You don't need to reconstruct full historical state often
- You want a lighter-weight solution with minimal database overhead

**Using both**: In some systems, you might use django-simple-history for critical business entities (orders, contracts, user profiles) and django-auditlog for high-volume operational data (logs, metrics, temporary records).

django-simple-history
---------------------

django-simple-history automatically creates a parallel "historical" model for each tracked model, storing a complete snapshot on every create, update, and delete.

Installation
^^^^^^^^^^^^

Add the package to your requirements:

.. code-block:: text

    # requirements/base.txt
    django-simple-history==3.11.0

Configure Django settings:

.. code-block:: python

    # config/settings/base.py
    INSTALLED_APPS = [
        # ... Django apps ...
        "simple_history",
        # ... your apps ...
    ]

    MIDDLEWARE = [
        # ... other middleware ...
        "simple_history.middleware.HistoryRequestMiddleware",
    ]

The middleware automatically captures the current user from the request, so historical records include who made each change.

Run migrations to create the history tables:

.. code-block:: bash

    docker compose -f docker-compose.local.yml run --rm django python manage.py migrate

Adding History to Models
^^^^^^^^^^^^^^^^^^^^^^^^

Add ``HistoricalRecords`` to any model you want to track:

.. code-block:: python

    # {project_slug}/orders/models.py
    from django.db import models
    from simple_history.models import HistoricalRecords

    from {project_slug}.core.models import BaseModel


    class Order(BaseModel):
        status = models.CharField(max_length=50, default="pending")
        total = models.DecimalField(max_digits=10, decimal_places=2)
        customer_notes = models.TextField(blank=True)
        internal_notes = models.TextField(blank=True)

        history = HistoricalRecords()

        def __str__(self):
            return f"Order {self.id} - {self.status}"

This creates a ``HistoricalOrder`` model with all the same fields plus:

- ``history_id``: Primary key for the historical record
- ``history_date``: When the change occurred (indexed by default)
- ``history_type``: ``+`` (create), ``~`` (update), or ``-`` (delete)
- ``history_user``: The user who made the change (via middleware)
- ``history_change_reason``: Optional explanation for the change

Generate and run migrations:

.. code-block:: bash

    docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations
    docker compose -f docker-compose.local.yml run --rm django python manage.py migrate

Excluding Fields
""""""""""""""""

For fields that change frequently but don't need tracking (like ``last_login`` or cache fields), exclude them:

.. code-block:: python

    class Order(BaseModel):
        # ... fields ...
        cache_key = models.CharField(max_length=100, blank=True)

        history = HistoricalRecords(excluded_fields=["cache_key"])

For fields inherited from ``BaseModel``, you may want to exclude ``last_modified_at`` since the history already tracks timestamps:

.. code-block:: python

    history = HistoricalRecords(excluded_fields=["last_modified_at"])

Querying History
^^^^^^^^^^^^^^^^

Access historical records through the ``history`` manager:

.. code-block:: python

    # {project_slug}/orders/selectors.py
    from datetime import datetime
    from django.db.models import QuerySet

    from .models import Order


    def order_history(*, order: Order) -> QuerySet:
        """Return all historical versions of an order."""
        return order.history.all()


    def order_as_of(*, order_id: int, timestamp: datetime) -> Order:
        """Return the order's state at a specific point in time."""
        return Order.history.as_of(timestamp).get(id=order_id)


    def order_changes_by_user(*, user_id: int) -> QuerySet:
        """Return all order changes made by a specific user."""
        return Order.history.filter(history_user_id=user_id)


    def order_recent_changes(*, hours: int = 24) -> QuerySet:
        """Return orders changed in the last N hours."""
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=hours)
        return Order.history.filter(history_date__gte=cutoff)

Comparing Versions
""""""""""""""""""

Use ``diff_against()`` to see what changed between versions:

.. code-block:: python

    # {project_slug}/orders/services.py
    def order_get_changes(*, order: Order) -> list[dict]:
        """Return a list of changes for an order."""
        changes = []
        history = order.history.all()

        for i, record in enumerate(history):
            if record.prev_record:
                delta = record.diff_against(record.prev_record)
                changes.append({
                    "date": record.history_date,
                    "user": record.history_user,
                    "type": record.history_type,
                    "changes": [
                        {
                            "field": change.field,
                            "old": change.old,
                            "new": change.new,
                        }
                        for change in delta.changes
                    ],
                })
        return changes

Setting Change Reasons
""""""""""""""""""""""

Add context to changes by setting a reason:

.. code-block:: python

    # In a service function
    from simple_history.utils import update_change_reason

    def order_cancel(*, order: Order, reason: str, cancelled_by: User) -> Order:
        """Cancel an order with a documented reason."""
        order.status = "cancelled"
        order.save()
        update_change_reason(order, f"Cancelled: {reason}")
        return order

Admin Integration
^^^^^^^^^^^^^^^^^

Use ``SimpleHistoryAdmin`` to add history viewing and revert functionality:

.. code-block:: python

    # {project_slug}/orders/admin.py
    from django.contrib import admin
    from simple_history.admin import SimpleHistoryAdmin

    from .models import Order


    @admin.register(Order)
    class OrderAdmin(SimpleHistoryAdmin):
        list_display = ["id", "status", "total", "created_at"]
        list_filter = ["status"]
        search_fields = ["id"]

        # Fields to show in the history list view
        history_list_display = ["status", "total"]

This adds a "History" button to each order's change page, showing all versions with the ability to view details and revert to any previous state.

Disabling Revert in Production
""""""""""""""""""""""""""""""

If you want history viewing without revert capability:

.. code-block:: python

    # config/settings/production.py
    SIMPLE_HISTORY_REVERT_DISABLED = True

Bulk Operations
^^^^^^^^^^^^^^^

Standard ``bulk_create()`` and ``bulk_update()`` bypass signals and won't create history. Use the provided utilities:

.. code-block:: python

    # {project_slug}/orders/services.py
    from simple_history.utils import bulk_create_with_history, bulk_update_with_history

    from .models import Order


    def orders_bulk_create(*, orders_data: list[dict]) -> list[Order]:
        """Create multiple orders with history tracking."""
        orders = [Order(**data) for data in orders_data]
        return bulk_create_with_history(orders, Order)


    def orders_bulk_update_status(*, orders: list[Order], status: str) -> list[Order]:
        """Update status for multiple orders with history tracking."""
        for order in orders:
            order.status = status
        bulk_update_with_history(orders, Order, ["status"])
        return orders

django-auditlog
---------------

django-auditlog stores changes as JSON deltas in a single ``LogEntry`` table, providing a lightweight audit trail without the storage overhead of full snapshots.

Installation
^^^^^^^^^^^^

Add the package to your requirements:

.. code-block:: text

    # requirements/base.txt
    django-auditlog==3.3.0

Configure Django settings:

.. code-block:: python

    # config/settings/base.py
    INSTALLED_APPS = [
        # ... Django apps ...
        "auditlog",
        # ... your apps ...
    ]

    MIDDLEWARE = [
        # ... other middleware ...
        "auditlog.middleware.AuditlogMiddleware",
    ]

Run migrations:

.. code-block:: bash

    docker compose -f docker-compose.local.yml run --rm django python manage.py migrate

Registering Models
^^^^^^^^^^^^^^^^^^

Register models in ``AppConfig.ready()`` for clean separation in the modular monolith:

.. code-block:: python

    # {project_slug}/orders/apps.py
    from django.apps import AppConfig


    class OrdersConfig(AppConfig):
        name = "{project_slug}.orders"
        verbose_name = "Orders"

        def ready(self):
            from auditlog.registry import auditlog
            from .models import Order, OrderItem

            auditlog.register(Order)
            auditlog.register(OrderItem)

Alternative: Use the decorator directly on models:

.. code-block:: python

    # {project_slug}/orders/models.py
    from auditlog.registry import auditlog

    from {project_slug}.core.models import BaseModel


    @auditlog.register()
    class Order(BaseModel):
        status = models.CharField(max_length=50, default="pending")
        total = models.DecimalField(max_digits=10, decimal_places=2)

The registry approach is preferred in a modular monolith because it keeps model definitions clean and centralizes registration in the app configuration.

Include and Exclude Fields
^^^^^^^^^^^^^^^^^^^^^^^^^^

Control which fields are tracked:

.. code-block:: python

    # {project_slug}/orders/apps.py
    def ready(self):
        from auditlog.registry import auditlog
        from .models import Order

        # Only track specific fields
        auditlog.register(
            Order,
            include_fields=["status", "total"],
        )

        # Or exclude fields you don't care about
        auditlog.register(
            Order,
            exclude_fields=["internal_notes", "last_modified_at"],
        )

Querying Audit Logs
^^^^^^^^^^^^^^^^^^^

Query the ``LogEntry`` model to retrieve audit information:

.. code-block:: python

    # {project_slug}/orders/selectors.py
    from auditlog.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import QuerySet

    from .models import Order


    def order_audit_log(*, order: Order) -> QuerySet[LogEntry]:
        """Return all audit log entries for an order."""
        return LogEntry.objects.get_for_object(order)


    def orders_changed_by_user(*, user_id: int) -> QuerySet[LogEntry]:
        """Return all order-related changes by a specific user."""
        content_type = ContentType.objects.get_for_model(Order)
        return LogEntry.objects.filter(
            content_type=content_type,
            actor_id=user_id,
        )


    def audit_log_for_period(*, start_date, end_date) -> QuerySet[LogEntry]:
        """Return all audit entries within a date range."""
        return LogEntry.objects.filter(
            timestamp__range=(start_date, end_date),
        ).select_related("content_type", "actor")

Understanding LogEntry Fields
"""""""""""""""""""""""""""""

Each ``LogEntry`` contains:

.. code-block:: python

    log_entry.content_type     # The model that was changed
    log_entry.object_pk        # Primary key of the changed object
    log_entry.object_repr      # String representation at time of change
    log_entry.action           # 0=create, 1=update, 2=delete
    log_entry.changes          # JSON dict of field changes
    log_entry.actor            # User who made the change
    log_entry.timestamp        # When the change occurred
    log_entry.remote_addr      # IP address (if middleware configured)

The ``changes`` field contains the old and new values:

.. code-block:: python

    # Example changes dict for an update
    {
        "status": ["pending", "shipped"],
        "total": ["99.99", "109.99"],
    }

Access changes programmatically:

.. code-block:: python

    def format_audit_entry(log_entry: LogEntry) -> dict:
        """Format a log entry for display."""
        action_names = {0: "created", 1: "updated", 2: "deleted"}
        return {
            "action": action_names.get(log_entry.action, "unknown"),
            "model": log_entry.content_type.model,
            "object_id": log_entry.object_pk,
            "user": str(log_entry.actor) if log_entry.actor else "system",
            "timestamp": log_entry.timestamp,
            "changes": log_entry.changes,
        }

Admin Integration
^^^^^^^^^^^^^^^^^

View audit logs in the Django admin:

.. code-block:: python

    # {project_slug}/orders/admin.py
    from auditlog.models import LogEntry
    from django.contrib import admin


    @admin.register(LogEntry)
    class LogEntryAdmin(admin.ModelAdmin):
        list_display = [
            "timestamp",
            "content_type",
            "object_repr",
            "action",
            "actor",
        ]
        list_filter = ["action", "content_type", "timestamp"]
        search_fields = ["object_repr", "actor__email"]
        readonly_fields = [
            "content_type",
            "object_pk",
            "object_repr",
            "action",
            "changes",
            "actor",
            "timestamp",
        ]

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

Integration with Domain Events
------------------------------

Connect audit logging to the modular monolith's domain event system. This enables other modules to react to audit events without direct coupling.

Define an Audit Event
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # {project_slug}/domain_events/events.py
    from dataclasses import dataclass, field
    from datetime import datetime

    from .base import DomainEvent


    @dataclass
    class ModelAuditedEvent(DomainEvent):
        """Emitted when a model is created, updated, or deleted."""

        model_name: str
        instance_id: int
        action: str  # "create", "update", "delete"
        changed_fields: list[str] = field(default_factory=list)
        changed_by_id: int | None = None
        timestamp: datetime = field(default_factory=datetime.now)

Emit Events from django-simple-history
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use the ``post_create_historical_record`` signal:

.. code-block:: python

    # {project_slug}/core/audit_events.py
    from django.dispatch import receiver
    from simple_history.signals import post_create_historical_record

    from {project_slug}.domain_events.bus import event_bus
    from {project_slug}.domain_events.events import ModelAuditedEvent


    ACTION_MAP = {
        "+": "create",
        "~": "update",
        "-": "delete",
    }


    @receiver(post_create_historical_record)
    def emit_audit_domain_event(sender, instance, history_instance, **kwargs):
        """Emit a domain event when a historical record is created."""
        # Get changed fields by comparing to previous record
        changed_fields = []
        if history_instance.prev_record:
            delta = history_instance.diff_against(history_instance.prev_record)
            changed_fields = [change.field for change in delta.changes]

        event = ModelAuditedEvent(
            model_name=instance.__class__.__name__,
            instance_id=instance.pk,
            action=ACTION_MAP.get(history_instance.history_type, "unknown"),
            changed_fields=changed_fields,
            changed_by_id=(
                history_instance.history_user.id
                if history_instance.history_user
                else None
            ),
            timestamp=history_instance.history_date,
        )
        event_bus.publish(event)

Register the signal handler in your app config:

.. code-block:: python

    # {project_slug}/core/apps.py
    from django.apps import AppConfig


    class CoreConfig(AppConfig):
        name = "{project_slug}.core"
        verbose_name = "Core"

        def ready(self):
            from . import audit_events  # noqa: F401

Emit Events from django-auditlog
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use auditlog's post-log signal:

.. code-block:: python

    # {project_slug}/core/audit_events.py
    from auditlog.models import LogEntry
    from django.db.models.signals import post_save
    from django.dispatch import receiver

    from {project_slug}.domain_events.bus import event_bus
    from {project_slug}.domain_events.events import ModelAuditedEvent


    ACTION_MAP = {
        LogEntry.Action.CREATE: "create",
        LogEntry.Action.UPDATE: "update",
        LogEntry.Action.DELETE: "delete",
    }


    @receiver(post_save, sender=LogEntry)
    def emit_audit_domain_event(sender, instance, created, **kwargs):
        """Emit a domain event when an audit log entry is created."""
        if not created:
            return

        changed_fields = list(instance.changes.keys()) if instance.changes else []

        event = ModelAuditedEvent(
            model_name=instance.content_type.model,
            instance_id=int(instance.object_pk),
            action=ACTION_MAP.get(instance.action, "unknown"),
            changed_fields=changed_fields,
            changed_by_id=instance.actor_id,
            timestamp=instance.timestamp,
        )
        event_bus.publish(event)

Subscribe to Audit Events
^^^^^^^^^^^^^^^^^^^^^^^^^

Other modules can react to audit events:

.. code-block:: python

    # {project_slug}/notifications/handlers.py
    import structlog

    from {project_slug}.domain_events.bus import event_bus
    from {project_slug}.domain_events.events import ModelAuditedEvent

    logger = structlog.get_logger(__name__)


    def handle_sensitive_model_change(event: ModelAuditedEvent):
        """Alert on changes to sensitive models."""
        sensitive_models = {"user", "payment", "contract"}

        if event.model_name.lower() in sensitive_models:
            logger.warning(
                "sensitive_model_changed",
                model=event.model_name,
                instance_id=event.instance_id,
                action=event.action,
                changed_by=event.changed_by_id,
            )
            # Send alert, create compliance record, etc.


    # Register in apps.py ready()
    event_bus.subscribe(ModelAuditedEvent, handle_sensitive_model_change)

Testing Audit Functionality
---------------------------

django-simple-history Tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # {project_slug}/orders/tests/test_audit.py
    import pytest
    from django.utils import timezone
    from datetime import timedelta

    from {project_slug}.orders.models import Order
    from {project_slug}.orders.tests.factories import OrderFactory


    @pytest.mark.django_db
    class TestOrderHistory:
        def test_create_generates_history_record(self):
            order = OrderFactory()

            assert order.history.count() == 1
            record = order.history.first()
            assert record.history_type == "+"

        def test_update_generates_history_record(self):
            order = OrderFactory(status="pending")
            order.status = "shipped"
            order.save()

            assert order.history.count() == 2
            latest = order.history.first()
            assert latest.history_type == "~"
            assert latest.status == "shipped"

        def test_delete_generates_history_record(self):
            order = OrderFactory()
            order_id = order.id
            order.delete()

            # History persists after deletion
            history = Order.history.filter(id=order_id)
            assert history.count() == 2
            assert history.first().history_type == "-"

        def test_as_of_returns_historical_state(self):
            order = OrderFactory(status="pending")
            created_time = timezone.now()

            # Wait briefly and update
            order.status = "shipped"
            order.save()

            # Query historical state
            historical = Order.history.as_of(created_time)
            assert historical.filter(id=order.id).first().status == "pending"

        def test_diff_against_shows_changes(self):
            order = OrderFactory(status="pending", total=100)
            order.status = "shipped"
            order.total = 150
            order.save()

            latest = order.history.first()
            delta = latest.diff_against(latest.prev_record)

            field_names = [change.field for change in delta.changes]
            assert "status" in field_names
            assert "total" in field_names

        def test_history_user_captured_from_request(self, client, user):
            client.force_login(user)

            # Make a change through a view that triggers history
            # (Implementation depends on your views)
            order = OrderFactory()
            order.status = "updated_via_view"
            order.save()

            # In actual request context, history_user would be set
            # This test demonstrates the pattern

django-auditlog Tests
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # {project_slug}/orders/tests/test_audit.py
    import pytest
    from auditlog.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    from {project_slug}.orders.models import Order
    from {project_slug}.orders.tests.factories import OrderFactory


    @pytest.mark.django_db
    class TestOrderAuditLog:
        def test_create_generates_log_entry(self):
            order = OrderFactory()

            entries = LogEntry.objects.get_for_object(order)
            assert entries.count() == 1
            assert entries.first().action == LogEntry.Action.CREATE

        def test_update_generates_log_entry_with_changes(self):
            order = OrderFactory(status="pending")
            order.status = "shipped"
            order.save()

            entries = LogEntry.objects.get_for_object(order)
            update_entry = entries.filter(action=LogEntry.Action.UPDATE).first()

            assert update_entry is not None
            assert "status" in update_entry.changes
            assert update_entry.changes["status"] == ["pending", "shipped"]

        def test_excluded_fields_not_logged(self):
            # Assuming internal_notes is excluded
            order = OrderFactory(internal_notes="secret")
            order.internal_notes = "updated secret"
            order.save()

            entries = LogEntry.objects.get_for_object(order)
            for entry in entries:
                assert "internal_notes" not in (entry.changes or {})

        def test_actor_captured_from_middleware(self, rf, user):
            from auditlog.context import set_actor

            with set_actor(user):
                order = OrderFactory()

            entry = LogEntry.objects.get_for_object(order).first()
            assert entry.actor == user

Performance Considerations
--------------------------

History Table Growth
^^^^^^^^^^^^^^^^^^^^

Both approaches create additional database records. Plan for growth:

**django-simple-history**: Each tracked model gets its own history table. A model with 1 million rows that averages 5 updates per record will have ~5 million history rows.

.. code-block:: python

    # Check history table size
    from {project_slug}.orders.models import Order

    total_orders = Order.objects.count()
    total_history = Order.history.count()
    avg_versions = total_history / total_orders if total_orders else 0

**django-auditlog**: All changes go to a single ``LogEntry`` table. Monitor its size:

.. code-block:: python

    from auditlog.models import LogEntry

    total_entries = LogEntry.objects.count()
    entries_per_day = LogEntry.objects.filter(
        timestamp__date=timezone.now().date()
    ).count()

Indexing
^^^^^^^^

django-simple-history automatically indexes ``history_date`` (since version 3.1). For django-auditlog, consider adding indexes for common queries:

.. code-block:: python

    # Custom migration for auditlog
    from django.db import migrations, models


    class Migration(migrations.Migration):
        dependencies = [
            ("auditlog", "0001_initial"),
        ]

        operations = [
            migrations.AddIndex(
                model_name="logentry",
                index=models.Index(
                    fields=["content_type", "object_pk"],
                    name="auditlog_content_object_idx",
                ),
            ),
        ]

Archiving Old History
^^^^^^^^^^^^^^^^^^^^^

For long-running systems, archive or delete old history:

.. code-block:: python

    # {project_slug}/core/management/commands/archive_audit_history.py
    from datetime import timedelta

    from django.core.management.base import BaseCommand
    from django.utils import timezone


    class Command(BaseCommand):
        help = "Archive audit history older than specified days"

        def add_arguments(self, parser):
            parser.add_argument(
                "--days",
                type=int,
                default=365,
                help="Archive history older than this many days",
            )
            parser.add_argument(
                "--dry-run",
                action="store_true",
                help="Show what would be archived without deleting",
            )

        def handle(self, *args, **options):
            cutoff = timezone.now() - timedelta(days=options["days"])

            # For django-simple-history
            from {project_slug}.orders.models import Order

            old_history = Order.history.filter(history_date__lt=cutoff)
            count = old_history.count()

            if options["dry_run"]:
                self.stdout.write(f"Would archive {count} Order history records")
            else:
                old_history.delete()
                self.stdout.write(f"Archived {count} Order history records")

Common Patterns
---------------

Compliance Reporting
^^^^^^^^^^^^^^^^^^^^

Generate audit reports for compliance requirements:

.. code-block:: python

    # {project_slug}/orders/selectors.py
    from datetime import datetime
    from django.db.models import QuerySet

    from .models import Order


    def order_audit_report(
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> QuerySet:
        """Generate an audit report for orders in a date range."""
        return (
            Order.history.filter(history_date__range=(start_date, end_date))
            .select_related("history_user")
            .values(
                "id",
                "history_date",
                "history_type",
                "history_user__email",
                "status",
                "total",
            )
            .order_by("id", "history_date")
        )


    def changes_by_user_report(*, user_id: int) -> list[dict]:
        """Report all changes made by a specific user."""
        from collections import defaultdict

        changes = defaultdict(list)

        for record in Order.history.filter(history_user_id=user_id):
            changes[record.id].append({
                "date": record.history_date,
                "type": record.history_type,
                "status": record.status,
            })

        return dict(changes)

API Endpoints for Audit History
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Expose history through your API:

.. code-block:: python

    # {project_slug}/orders/api/serializers.py
    from rest_framework import serializers


    class OrderHistorySerializer(serializers.Serializer):
        history_id = serializers.IntegerField()
        history_date = serializers.DateTimeField()
        history_type = serializers.CharField()
        history_user = serializers.SerializerMethodField()
        status = serializers.CharField()
        total = serializers.DecimalField(max_digits=10, decimal_places=2)

        def get_history_user(self, obj):
            if obj.history_user:
                return obj.history_user.email
            return None


    # {project_slug}/orders/api/views.py
    from rest_framework import viewsets
    from rest_framework.decorators import action
    from rest_framework.response import Response

    from ..models import Order
    from .serializers import OrderHistorySerializer, OrderSerializer


    class OrderViewSet(viewsets.ModelViewSet):
        queryset = Order.objects.all()
        serializer_class = OrderSerializer

        @action(detail=True, methods=["get"])
        def history(self, request, pk=None):
            """Return the change history for this order."""
            order = self.get_object()
            history = order.history.all().select_related("history_user")
            serializer = OrderHistorySerializer(history, many=True)
            return Response(serializer.data)

Soft Deletes with History
^^^^^^^^^^^^^^^^^^^^^^^^^

Combine soft deletes with audit history:

.. code-block:: python

    # {project_slug}/orders/models.py
    from django.db import models
    from simple_history.models import HistoricalRecords

    from {project_slug}.core.models import BaseModel


    class OrderQuerySet(models.QuerySet):
        def active(self):
            return self.filter(deleted_at__isnull=True)


    class Order(BaseModel):
        status = models.CharField(max_length=50, default="pending")
        total = models.DecimalField(max_digits=10, decimal_places=2)
        deleted_at = models.DateTimeField(null=True, blank=True)

        objects = OrderQuerySet.as_manager()
        history = HistoricalRecords()

        def soft_delete(self):
            from django.utils import timezone

            self.deleted_at = timezone.now()
            self.save()  # This creates a history record

The history record shows when and by whom the soft delete occurred.

See Also
--------

- :doc:`service-layer-patterns` - Organize audit-related business logic in services
- :doc:`event-driven-architecture` - Emit domain events on model changes
- :doc:`observability-logging` - Structured logging for audit trail debugging

.. _django-simple-history: https://django-simple-history.readthedocs.io/
.. _django-auditlog: https://django-auditlog.readthedocs.io/
