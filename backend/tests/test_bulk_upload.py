import io
import csv
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from core.models import Application, TestCase as TestCaseModel


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class BulkUploadAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_authenticate(user=self.user)
        self.app = Application.objects.create(
            user=self.user,
            url='http://example.com',
            base_url='http://example.com',
            status='idle'
        )

    def test_bulk_upload_csv_preview_and_import(self):
        csv_content = (
            "Title,Category,Expected Result,Steps\n"
            "Verify User Login,Generic,User lands on dashboard,\"1. Go to http://example.com/login\n2. Fill #email with admin@example.com\n3. Click #submit\"\n"
            "Verify Password Reset,Generic,Reset email sent,\"1. Go to http://example.com/reset\n2. Fill #email with user@example.com\n3. Click #send\"\n"
        )
        csv_file = SimpleUploadedFile("test_cases.csv", csv_content.encode('utf-8'), content_type="text/csv")

        # Test Async File Upload Handoff
        response = self.client.post('/api/test-cases/bulk_upload/', {
            'app_id': self.app.id,
            'file': csv_file,
            'preview': 'true'
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)

        # Test Import Commit via Pre-parsed JSON payload
        response_import = self.client.post('/api/test-cases/bulk_upload/', {
            'app_id': self.app.id,
            'test_cases': [
                {
                    "title": "Verify User Login",
                    "category": "Generic",
                    "expected_result": "User lands on dashboard",
                    "steps": [{"action": "navigate", "target": "http://example.com/login"}]
                }
            ]
        }, format='json')

        self.assertEqual(response_import.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response_import.data['created_count'], 1)
        self.assertEqual(TestCaseModel.objects.filter(app=self.app).count(), 1)

    def test_bulk_upload_excel_import(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Title", "Category", "Expected Result", "Steps"])
        ws.append(["Checkout Flow", "Industry Flow", "Cart updated", "1. Click #checkout button"])
        
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        
        excel_file = SimpleUploadedFile("test_cases.xlsx", stream.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response = self.client.post('/api/test-cases/bulk_upload/', {
            'app_id': self.app.id,
            'file': excel_file,
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)

    def test_bulk_upload_unsupported_format(self):
        dummy_file = SimpleUploadedFile("test.txt", b"invalid format", content_type="text/plain")
        response = self.client.post('/api/test-cases/bulk_upload/', {
            'app_id': self.app.id,
            'file': dummy_file,
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Unsupported file format", response.data['error'])

    def test_bulk_upload_pdf_async(self):
        pdf_file = SimpleUploadedFile("test.pdf", b"%PDF-1.4 header content", content_type="application/pdf")
        response = self.client.post('/api/test-cases/bulk_upload/', {
            'app_id': self.app.id,
            'file': pdf_file,
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)
