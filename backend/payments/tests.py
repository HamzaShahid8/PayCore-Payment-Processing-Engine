from unittest.mock import patch
from uuid import uuid4

import stripe
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payments.models import Payment, StripeWebhookEvent


@override_settings(
    STRIPE_SECRET_KEY="sk_test_unit",
    STRIPE_WEBHOOK_SECRET="whsec_unit",
    STRIPE_SUCCESS_URL="https://frontend.example/success",
    STRIPE_CANCEL_URL="https://frontend.example/cancel",
)
class PaymentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("payments.services.stripe.checkout.Session.create")
    def test_creates_checkout_session_for_each_fixed_plan(self, create_session):
        create_session.side_effect = lambda **kwargs: {
            "id": f"cs_test_{kwargs['metadata']['plan']}",
            "url": "https://checkout.stripe.com/test",
        }
        plans_and_cents = {
            "basic": 1_000,
            "standard": 51_000,
            "premium": 100_000,
            "enterprise": 325_700,
        }

        for plan, amount_cents in plans_and_cents.items():
            with self.subTest(plan=plan):
                response = self.client.post(
                    "/api/create-checkout-session",
                    {"plan": plan},
                    format="json",
                )

                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    response.json(),
                    {
                        "success": True,
                        "session_id": f"cs_test_{plan}",
                        "checkout_url": "https://checkout.stripe.com/test",
                    },
                )
                call = create_session.call_args.kwargs
                self.assertEqual(call["mode"], "payment")
                self.assertEqual(
                    call["line_items"][0]["price_data"]["unit_amount"], amount_cents
                )
                self.assertEqual(call["metadata"]["plan"], plan)
                self.assertEqual(call["success_url"], "https://frontend.example/success")
                self.assertEqual(call["cancel_url"], "https://frontend.example/cancel")

        self.assertEqual(Payment.objects.count(), len(plans_and_cents))

    def test_rejects_missing_or_unknown_plan(self):
        for data in ({}, {"plan": "custom"}, {"plan": "basic", "amount": 1}):
            with self.subTest(data=data):
                response = self.client.post(
                    "/api/create-checkout-session", data, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])

    @patch(
        "payments.services.stripe.checkout.Session.create",
        side_effect=stripe.StripeError("temporary Stripe failure"),
    )
    def test_stripe_checkout_failure_returns_502_and_marks_attempt_failed(
        self, create_session
    ):
        response = self.client.post(
            "/api/create-checkout-session",
            {"plan": "basic"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "stripe_error")
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)
        create_session.assert_called_once()

    def test_rejects_unsupported_method_with_json_error(self):
        response = self.client.get("/api/create-checkout-session")
        self.assertEqual(response.status_code, 405)
        self.assertFalse(response.json()["success"])

    def test_invalid_webhook_signature_is_rejected(self):
        response = self.client.generic(
            "POST",
            "/api/stripe/webhook",
            data=b'{"id":"evt_invalid","type":"checkout.session.completed"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=invalid",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_webhook")
        self.assertEqual(StripeWebhookEvent.objects.count(), 0)

    @patch("payments.services.stripe.Webhook.construct_event")
    def test_paid_checkout_webhook_updates_payment_and_is_idempotent(self, construct_event):
        payment = Payment.objects.create(
            plan="basic",
            amount_cents=1_000,
            stripe_checkout_session_id="cs_test_paid",
        )
        event = {
            "id": "evt_paid_once",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_paid",
                    "payment_status": "paid",
                    "amount_total": 1_000,
                    "currency": "usd",
                    "payment_intent": "pi_test_paid",
                    "metadata": {"payment_id": str(payment.id), "plan": "basic"},
                    "customer_details": {"email": "payer@example.com"},
                }
            },
        }
        construct_event.return_value = event
        request_body = b'{"id":"evt_paid_once","type":"checkout.session.completed"}'

        first_response = self.client.generic(
            "POST",
            "/api/stripe/webhook",
            data=request_body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
        )
        second_response = self.client.generic(
            "POST",
            "/api/stripe/webhook",
            data=request_body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertFalse(first_response.json()["duplicate"])
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()["duplicate"])
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.stripe_payment_intent_id, "pi_test_paid")
        self.assertEqual(payment.customer_email, "payer@example.com")
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(StripeWebhookEvent.objects.count(), 1)
        self.assertEqual(
            construct_event.call_args.kwargs["payload"],
            request_body,
        )

    @patch("payments.services.stripe.Webhook.construct_event")
    def test_unpaid_checkout_is_not_marked_paid(self, construct_event):
        payment = Payment.objects.create(
            plan="standard",
            amount_cents=51_000,
            stripe_checkout_session_id="cs_test_unpaid",
        )
        construct_event.return_value = {
            "id": f"evt_unpaid_{uuid4()}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_unpaid",
                    "payment_status": "unpaid",
                    "amount_total": 51_000,
                    "currency": "usd",
                    "metadata": {"payment_id": str(payment.id)},
                }
            },
        }

        response = self.client.generic(
            "POST",
            "/api/stripe/webhook",
            data=b'{"type":"checkout.session.completed"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @patch("payments.services.stripe.Webhook.construct_event")
    def test_paid_webhook_with_mismatched_amount_is_not_applied(self, construct_event):
        payment = Payment.objects.create(
            plan="basic",
            amount_cents=1_000,
            stripe_checkout_session_id="cs_test_wrong_amount",
        )
        construct_event.return_value = {
            "id": f"evt_wrong_amount_{uuid4()}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_wrong_amount",
                    "payment_status": "paid",
                    "amount_total": 1,
                    "currency": "usd",
                    "metadata": {"payment_id": str(payment.id)},
                }
            },
        }

        response = self.client.generic(
            "POST",
            "/api/stripe/webhook",
            data=b'{"type":"checkout.session.completed"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
