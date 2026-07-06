from rest_framework.renderers import JSONRenderer

class GlobalJSONRenderer(JSONRenderer):
    """
    Wraps all JSON responses in a standard structure:
    {
        "status_code": int,
        "success": bool,
        "data": actual_response_payload
    }
    """
    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = 200
        if renderer_context:
            status_code = renderer_context['response'].status_code

        # HTTP 204 No Content and HTTP 304 Not Modified must not return a body.
        # If we return a body for 204, it violates the HTTP protocol and causes
        # "Broken pipe" connection errors on clients like Axios/browsers.
        if status_code in (204, 304):
            return super().render(data, accepted_media_type, renderer_context)

        # Avoid double-wrapping if the data is already structured by our handlers
        if isinstance(data, dict) and 'status_code' in data and 'success' in data:
            wrapped_data = data
        else:
            wrapped_data = {
                'status_code': status_code,
                'success': status_code < 400,
                'data': data
            }

        return super().render(wrapped_data, accepted_media_type, renderer_context)
