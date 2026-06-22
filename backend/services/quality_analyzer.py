import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ResponseQualityAnalyzer:
    @staticmethod
    def check_content_errors(status, body_text):
        """
        Scans status codes and response bodies for error flags and database/server traces.
        """
        if not body_text:
            return None
            
        # Status code >= 400 is already a connection/status error, handled separately.
        if status >= 400:
            return None

        # Check JSON-based structures
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                # 1. success = false / success = "false"
                if data.get('success') is False or data.get('success') == 'false':
                    return "API response returned success=false flag."
                
                # 2. explicit error fields
                if 'error' in data or 'errors' in data:
                    err = data.get('error') or data.get('errors')
                    # Make sure it's not None or empty
                    if err:
                        return f"API response contains error field: {err}"
                        
                # 3. status = error / status = fail
                if data.get('status') in ['error', 'fail']:
                    msg = data.get('message') or data.get('detail') or 'Unknown failure message'
                    return f"API status is '{data.get('status')}': {msg}"
        except Exception:
            # Not JSON, check raw text for crash keywords
            lower_body = body_text.lower()
            
            # Check for database errors
            db_kws = ["sql error", "database error", "sqlite3.error", "postgresql error", "mysql error", "syntax error near"]
            if any(kw in lower_body for kw in db_kws):
                return "Database error trace or SQL syntax failure found in response body."
                
            # Check for backend tracebacks
            server_kws = ["traceback (most recent call", "nullpointerexception", "undefined index", "fatal error", "internal server error"]
            if any(kw in lower_body for kw in server_kws):
                return "Internal server exception or crash traceback found in response body."
                
        return None

    @staticmethod
    def get_json_keys(body_text):
        """
        Parses body text and returns a list of sorted keys if it is a JSON object,
        or keys from the first object if it is a list of JSON objects.
        """
        if not body_text:
            return []
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                return sorted(list(data.keys()))
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                return sorted(list(data[0].keys()))
        except Exception:
            pass
        return []

    @classmethod
    def detect_schema_regression(cls, current_call, previous_calls):
        """
        Compares current JSON keys with keys from the matching call in previous successful run.
        """
        url = current_call.get('url')
        method = current_call.get('method')
        
        # Strip query parameters for matching
        parsed_url = urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        
        current_body = current_call.get('body', '')
        current_keys = cls.get_json_keys(current_body)
        
        if not current_keys:
            return None

        # Find matching call in previous run
        for prev in previous_calls:
            prev_url = prev.get('url', '')
            prev_parsed = urlparse(prev_url)
            prev_normalized = f"{prev_parsed.scheme}://{prev_parsed.netloc}{prev_parsed.path}"
            
            if prev_normalized == normalized_url and prev.get('method') == method:
                prev_body = prev.get('body', '')
                prev_keys = cls.get_json_keys(prev_body)
                
                if prev_keys:
                    # Detect missing fields
                    missing_keys = [k for k in prev_keys if k not in current_keys]
                    if missing_keys:
                        return f"API schema regression: Missing fields {missing_keys} compared to last successful run."
        return None

    @classmethod
    def analyze_response_quality(cls, current_calls, previous_calls):
        """
        Runs quality scans and returns a list of detected warnings and errors.
        """
        issues = []
        
        for call in current_calls:
            url = call.get('url')
            method = call.get('method')
            status = call.get('status', 200)
            body = call.get('body', '')
            latency = call.get('latency', 0)  # in milliseconds
            
            # 1. Content Error checks
            content_err = cls.check_content_errors(status, body)
            if content_err:
                issues.append({
                    "url": url,
                    "method": method,
                    "type": "content_error",
                    "issue": content_err
                })
                
            # 2. Latency checks (> 2000ms is flagged as slow API warning)
            if latency > 2000:
                issues.append({
                    "url": url,
                    "method": method,
                    "type": "latency_warning",
                    "issue": f"High response latency detected ({latency}ms)."
                })
                
            # 3. Schema Regression checks (only compared against successful baseline)
            if previous_calls:
                regression = cls.detect_schema_regression(call, previous_calls)
                if regression:
                    issues.append({
                        "url": url,
                        "method": method,
                        "type": "schema_regression",
                        "issue": regression
                    })
                    
        return issues
