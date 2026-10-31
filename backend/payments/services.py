import logging
from collections.abc import Mapping
from uuid import UUID

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.models import Payment, StripeWebhookEvent

logger = logging.getLogger(__name__)

PLAN_AMOUNTS_CENTS = {
    "basic": 1_000,
    "standard": 51_000,
    "premium": 100_000,
    "enterprise": 325_700,
}


class StripeConfigurationError(Exception):
    pass


class StripeGatewayError(Exception):
    pass


class InvalidWebhookError(Exception):
    pass


def create_checkout_session(plan):
    amount_cents = PLAN_AMOUNTS_CENTS[plan]
    required_settings = (
        settings.STRIPE_SECRET_KEY,
        settings.STRIPE_SUCCESS_URL,
        settings.STRIPE_CANCEL_URL,
    )
    if not all(required_settings):
        raise StripeConfigurationError("Stripe Checkout is not fully configured.")

    payment = Payment.objects.create(plan=plan, amount_cents=amount_cents)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"{plan.title()} plan"},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=settings.STRIPE_SUCCESS_URL,
            cancel_url=settings.STRIPE_CANCEL_URL,
            client_reference_id=str(payment.id),
            metadata={"payment_id": str(payment.id), "plan": plan},
            payment_intent_data={
                "metadata": {"payment_id": str(payment.id), "plan": plan}
            },
            idempotency_key=f"checkout-{payment.id}",
        )
    except stripe.StripeError as exc:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        logger.warning("Stripe Checkout session creation failed for payment %s", payment.id)
        raise StripeGatewayError("Stripe could not create a Checkout Session.") from exc

    session_id = session.get("id")
    checkout_url = session.get("url")
    if not isinstance(session_id, str) or not isinstance(checkout_url, str):
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        logger.error("Stripe returned an incomplete Checkout Session for payment %s", payment.id)
        raise StripeGatewayError("Stripe returned an invalid Checkout Session.")

    payment.stripe_checkout_session_id = session_id
    payment.save(update_fields=["stripe_checkout_session_id", "updated_at"])
    return {"session_id": session_id, "checkout_url": checkout_url}


def process_stripe_webhook(payload, signature):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise StripeConfigurationError("Stripe webhook verification is not configured.")
    if not signature:
        raise InvalidWebhookError("Missing Stripe signature.")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise InvalidWebhookError("Invalid Stripe webhook signature or payload.") from exc

    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not isinstance(event_type, str):
        raise InvalidWebhookError("Stripe webhook event is missing required fields.")

    with transaction.atomic():
        webhook_event, created = StripeWebhookEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={"event_type": event_type},
        )
        if not created:
            return {"duplicate": True, "processed": True}

        if event_type in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }:
            event_data = event.get("data")
            session = event_data.get("object") if isinstance(event_data, Mapping) else None
            if not isinstance(session, Mapping):
                raise InvalidWebhookError("Stripe Checkout event is missing its session.")
            _record_completed_checkout(session)

        return {"duplicate": False, "processed": True}


def _record_completed_checkout(session):
    if session.get("payment_status") != "paid":
        return

    session_id = session.get("id")
    metadata = session.get("metadata") or {}
    payment_id = metadata.get("payment_id") or session.get("client_reference_id")

    payment = None
    if payment_id:
        try:
            payment_uuid = UUID(str(payment_id))
        except (ValueError, TypeError, AttributeError):
            payment_uuid = None
        if payment_uuid is not None:
            payment = Payment.objects.filter(pk=payment_uuid).first()

    if payment is None and session_id:
        payment = Payment.objects.filter(stripe_checkout_session_id=session_id).first()

    if payment is None:
        logger.warning("Received a paid Checkout Session with no matching payment record.")
        return

    if not isinstance(session_id, str):
        logger.error("Paid Checkout Session is missing its session ID.")
        return

    if (
        payment.stripe_checkout_session_id
        and payment.stripe_checkout_session_id != session_id
    ):
        logger.error("Checkout Session did not match payment record %s", payment.id)
        return

    if (
        session.get("amount_total") != payment.amount_cents
        or session.get("currency") != payment.currency
    ):
        logger.error("Checkout Session amount did not match payment record %s", payment.id)
        return

    payment.stripe_checkout_session_id = session_id or payment.stripe_checkout_session_id
    payment_intent = session.get("payment_intent")
    payment.stripe_payment_intent_id = (
        payment_intent if isinstance(payment_intent, str) else ""
    )
    customer_details = session.get("customer_details") or {}
    customer_email = customer_details.get("email") or session.get("customer_email") or ""
    payment.customer_email = customer_email
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(
        update_fields=[
            "stripe_checkout_session_id",
            "stripe_payment_intent_id",
            "customer_email",
            "status",
            "paid_at",
            "updated_at",
        ]
    )
