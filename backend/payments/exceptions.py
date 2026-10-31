import logging

from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.error(
            "Unhandled API exception",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return Response(
            {
                "success": False,
                "error": {
                    "code": "internal_error",
                    "message": "An internal server error occurred.",
                },
            },
            status=500,
        )

    if isinstance(exc, APIException):
        error_code = exc.default_code
    else:
        error_code = "request_error"
    detail = response.data.get("detail", response.data)
    message = str(detail) if isinstance(detail, str) else "The request could not be processed."
    response.data = {
        "success": False,
        "error": {
            "code": str(error_code),
            "message": message,
        },
    }
    return response
