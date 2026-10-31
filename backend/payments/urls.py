from django.urls import path

from payments.views import create_checkout_session_view, stripe_webhook_view

urlpatterns = [
    path("create-checkout-session", create_checkout_session_view, name="create-checkout-session"),
    path("stripe/webhook", stripe_webhook_view, name="stripe-webhook"),
]
