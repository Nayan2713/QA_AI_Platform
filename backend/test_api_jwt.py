import os
import sys
import django
import json
from django.test import Client

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qa_engine.settings')
django.setup()

from core.models import Application, TestCase
from django.contrib.auth import get_user_model
User = get_user_model()
from rest_framework_simplejwt.tokens import RefreshToken

app = Application.objects.first()
if not app:
    print("No app found")
    sys.exit(1)
user = app.user

# Generate JWT Token
refresh = RefreshToken.for_user(user)
access_token = str(refresh.access_token)

client = Client(SERVER_NAME='127.0.0.1')

headers = {
    'HTTP_AUTHORIZATION': f'Bearer {access_token}',
    'content_type': 'application/json'
}

payload = {
    "app": app.id,
    "title": "Test Creation via API",
    "category": "Generic",
    "expected_result": "Success",
    "steps": [
        {"action": "navigate", "target": "https://example.com"}
    ],
    "ai_generated": False
}

print("Testing POST...")
response = client.post('/api/test-cases/', data=json.dumps(payload), **headers)
print(f"Status: {response.status_code}")
if response.status_code != 201:
    print(f"Response: {response.content}")

if response.status_code == 201:
    tc_id = response.json().get('id')
    print(f"Testing PATCH for {tc_id}...")
    patch_payload = payload.copy()
    patch_payload["title"] = "Updated via API"
    response = client.patch(f'/api/test-cases/{tc_id}/', data=json.dumps(patch_payload), **headers)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response: {response.content}")
