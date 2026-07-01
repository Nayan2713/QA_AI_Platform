from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework import serializers
from core.models import Application
from core.serializers import ApplicationSerializer, TestCaseSerializer

class ApplicationSerializerTests(TestCase):
    def setUp(self):
        """Create a test user for application tests"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_valid_data(self):
        """Test serializer with valid data"""
        data = {
            'url': 'https://example.com',
            'base_url': 'https://example.com'
        }
        serializer = ApplicationSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_invalid_url(self):
        """Test serializer rejects invalid URL"""
        data = {
            'url': 'invalid-url',
            'base_url': 'https://example.com'
        }
        serializer = ApplicationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('url', serializer.errors)

class TestCaseSerializerTests(TestCase):
    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.app = Application.objects.create(
            user=self.user,
            url='https://example.com',
            base_url='https://example.com'
        )
    
    def test_valid_test_case(self):
        """Test serializer with valid test case"""
        data = {
            'app': self.app.id,
            'title': 'Test Form Submission',
            'steps': [
                {'action': 'navigate', 'target': 'https://example.com'},
                {'action': 'fill', 'selector': 'input', 'value': 'test'}
            ],
            'expected_result': 'Form submitted'
        }
        serializer = TestCaseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_empty_steps(self):
        """Test serializer rejects empty steps"""
        data = {
            'app': self.app.id,
            'title': 'Empty Test',
            'steps': [],
            'expected_result': 'Should fail'
        }
        serializer = TestCaseSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('steps', serializer.errors)
    
    def test_invalid_action(self):
        """Test serializer rejects invalid action"""
        data = {
            'app': self.app.id,
            'title': 'Invalid Test',
            'steps': [
                {'action': 'invalid_action', 'target': 'https://example.com'}
            ],
            'expected_result': 'Should fail'
        }
        serializer = TestCaseSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('steps', serializer.errors)

    def test_model_used_serialization(self):
        """Test model_used field is correctly retrieved from generation_context"""
        from core.models import TestCase as TestCaseModel
        from core.serializers import TestCaseListSerializer
        tc = TestCaseModel.objects.create(
            app=self.app,
            title='Test Model Used',
            steps=[{'action': 'navigate', 'target': 'https://example.com'}],
            expected_result='Success',
            generation_context={'model_used': 'ChatGPT (gpt-4o-mini)'}
        )
        serializer = TestCaseSerializer(tc)
        self.assertEqual(serializer.data['model_used'], 'ChatGPT (gpt-4o-mini)')
        
        list_serializer = TestCaseListSerializer(tc)
        self.assertEqual(list_serializer.data['model_used'], 'ChatGPT (gpt-4o-mini)')