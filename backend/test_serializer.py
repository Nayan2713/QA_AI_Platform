import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qa_engine.settings')
django.setup()

from core.models import Application, TestCase
from django.contrib.auth import get_user_model
User = get_user_model()
from core.serializers import TestCaseSerializer

app = Application.objects.first()
if not app:
    print("No app found at all.")
    sys.exit(1)

user = app.user

payload = {
    "app": app.id,
    "title": "Test Title",
    "category": "Generic",
    "expected_result": "Test result",
    "steps": [
        {"action": "navigate", "target": "https://example.com"}
    ],
    "ai_generated": False
}

class DummyRequest:
    def __init__(self, user):
        self.user = user
        self.method = 'POST'
        self.data = payload

request = DummyRequest(user)
serializer = TestCaseSerializer(data=payload, context={'request': request})
is_valid = serializer.is_valid()

print(f"Is valid: {is_valid}")
if not is_valid:
    print(f"Errors: {serializer.errors}")

# test saving
if is_valid:
    try:
        serializer.save()
        print("Successfully saved!")
    except Exception as e:
        print(f"Error on save: {e}")
