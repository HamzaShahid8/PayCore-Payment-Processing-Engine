from django.contrib import admin

from .models import Payment, StripeWebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "plan",
        "amount_cents",
        "currency",
        "status",
        "customer_email",
        "created_at",
    )
    list_filter = ("status", "plan", "currency", "created_at")
    search_fields = (
        "id",
        "customer_email",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
    )
    readonly_fields = (
        "id",
        "plan",
        "amount_cents",
        "currency",
        "status",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
        "customer_email",
        "created_at",
        "updated_at",
        "paid_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("stripe_event_id", "event_type", "processed_at")
    list_filter = ("event_type", "processed_at")
    search_fields = ("stripe_event_id", "event_type")
    readonly_fields = ("stripe_event_id", "event_type", "processed_at")
    ordering = ("-processed_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
