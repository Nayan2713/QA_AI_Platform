# c:\Users\USER\Desktop\MVP\backend\test_quality.py
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qa_engine.settings')
django.setup()

from services.quality_analyzer import ResponseQualityAnalyzer

def run_tests():
    print("=" * 60)
    print("Testing ResponseQualityAnalyzer Logic")
    print("=" * 60)

    # Test Case 1: Database Error Detection
    print("\n--- Test 1: Content Error (Database/SQL Trace) ---")
    body_text_db_error = "An error occurred: database error: no such table: auth_user"
    issue = ResponseQualityAnalyzer.check_content_errors(status=200, body_text=body_text_db_error)
    print(f"Input: HTTP 200, SQL trace in body")
    print(f"Result: {issue}")
    assert issue is not None, "Should have flagged SQL trace"

    # Test Case 2: API Failure Flags
    print("\n--- Test 2: Content Error (API success=false flag) ---")
    body_text_api_fail = '{"success": false, "error": "Invalid auth credentials"}'
    issue = ResponseQualityAnalyzer.check_content_errors(status=200, body_text=body_text_api_fail)
    print(f"Input: HTTP 200, success=false JSON")
    print(f"Result: {issue}")
    assert "success=false" in issue or "error" in issue, "Should have flagged success=false flag"

    # Test Case 3: Schema Regression Detection
    print("\n--- Test 3: Schema Regression (Missing fields) ---")
    current_call = {
        "url": "http://example.com/api/v1/users",
        "method": "GET",
        "body": '{"id": 1, "username": "admin"}'
    }
    previous_calls = [
        {
            "url": "http://example.com/api/v1/users",
            "method": "GET",
            "body": '{"id": 1, "username": "admin", "email": "admin@example.com", "role": "superuser"}'
        }
    ]
    issue = ResponseQualityAnalyzer.detect_schema_regression(current_call, previous_calls)
    print(f"Input keys: {ResponseQualityAnalyzer.get_json_keys(current_call['body'])}")
    print(f"Baseline keys: {ResponseQualityAnalyzer.get_json_keys(previous_calls[0]['body'])}")
    print(f"Result: {issue}")
    assert issue is not None, "Should have flagged missing 'email' and 'role' fields"

    # Test Case 4: Analyze Response Quality (Multi-check helper)
    print("\n--- Test 4: Full analyze_response_quality ---")
    current_calls = [
        {
            "url": "http://example.com/api/v1/users",
            "method": "GET",
            "status": 200,
            "body": '{"id": 1, "username": "admin"}',
            "latency": 2500  # Latency Warning
        },
        {
            "url": "http://example.com/api/v1/posts",
            "method": "POST",
            "status": 200,
            "body": '{"success": false, "error": "permission_denied"}',
            "latency": 150
        }
    ]
    issues = ResponseQualityAnalyzer.analyze_response_quality(
        current_calls=current_calls,
        previous_calls=previous_calls,
        expected_result="Get users list"
    )
    print("Found issues:")
    for i in issues:
        print(f" - [{i['type'].upper()}]: {i['issue']} (Endpoint: {i['method']} {i['url']})")

    print("\n" + "=" * 60)
    print("All logic tests passed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
