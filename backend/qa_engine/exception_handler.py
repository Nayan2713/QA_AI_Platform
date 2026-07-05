from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.db.utils import OperationalError
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """Custom exception handler for all API exceptions"""

    # Handle DB connection errors explicitly — these surface as stale
    # persistent connections being reused after Postgres drops them.
    # CONN_HEALTH_CHECKS=True in settings prevents most occurrences,
    # but we still return a clean 503 if one slips through.
    if isinstance(exc, OperationalError):
        logger.error(f"Database connection error: {str(exc)}", exc_info=True)
        return Response(
            {'detail': 'A database connection error occurred. Please retry your request.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Handle User/Object DoesNotExist errors (e.g. SimpleJWT refresh for deleted/invalid users)
    if isinstance(exc, ObjectDoesNotExist):
        request = context.get('request')
        path = request.path if request else ''
        
        if 'auth' in path or 'user' in str(exc).lower():
            logger.warning(f"Authentication ObjectDoesNotExist caught for path {path}: {str(exc)}")
            return Response(
                {'detail': 'No active account found for the given token.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        else:
            logger.warning(f"ObjectDoesNotExist caught for path {path}: {str(exc)}")
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_404_NOT_FOUND
            )

    # Get the standard exception handler first
    response = exception_handler(exc, context)

    if response is None:
        # Log unexpected exceptions
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
        return Response(
            {'detail': 'An unexpected error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Log the exception
    logger.warning(f"API Exception: {exc.__class__.__name__} - {str(exc)}")

    # Add custom error format
    if response.data and 'detail' not in response.data:
        response.data = {
            'detail': response.data,
            'status': response.status_code
        }

    return response