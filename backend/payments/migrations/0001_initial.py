import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("plan", models.CharField(max_length=32)),
                ("amount_cents", models.PositiveIntegerField()),
                ("currency", models.CharField(default="usd", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("paid", "Paid"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "stripe_checkout_session_id",
                    models.CharField(blank=True, max_length=255, null=True, unique=True),
                ),
                ("stripe_payment_intent_id", models.CharField(blank=True, max_length=255)),
                ("customer_email", models.EmailField(blank=True, max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="StripeWebhookEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("stripe_event_id", models.CharField(max_length=255, unique=True)),
                ("event_type", models.CharField(max_length=255)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
