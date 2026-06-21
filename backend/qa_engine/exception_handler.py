from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """Custom exception handler for all API exceptions"""
    
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