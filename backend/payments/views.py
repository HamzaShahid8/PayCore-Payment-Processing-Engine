from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from payments.serializers import CreateCheckoutSessionSerializer
from payments.services import (
    InvalidWebhookError,
    StripeConfigurationError,
    StripeGatewayError,
    create_checkout_session,
    process_stripe_webhook,
)


@api_view(["POST"])
def create_checkout_session_view(request):
    serializer = CreateCheckoutSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "error": {
                    "code": "invalid_request",
                    "message": "A valid plan is required.",
                    "details": serializer.errors,
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = create_checkout_session(serializer.validated_data["plan"])
    except StripeConfigurationError:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "payment_service_unavailable",
                    "message": "The payment service is not configured.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except StripeGatewayError:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "stripe_error",
                    "message": "A Checkout Session could not be created.",
                },
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "success": True,
            "session_id": session["session_id"],
            "checkout_url": session["checkout_url"],
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def stripe_webhook_view(request):
    try:
        result = process_stripe_webhook(
            payload=request._request.body,
            signature=request.META.get("HTTP_STRIPE_SIGNATURE", ""),
        )
    except InvalidWebhookError:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "invalid_webhook",
                    "message": "The Stripe webhook could not be verified.",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except StripeConfigurationError:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "webhook_not_configured",
                    "message": "Stripe webhook verification is not configured.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"success": True, "received": True, "duplicate": result["duplicate"]},
        status=status.HTTP_200_OK,
    )
