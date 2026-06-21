from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from core.models import Application

class ApplicationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_create_application(self):
        """Test creating a new application"""
        data = {
            'url': 'https://example.com',
            'base_url': 'https://example.com'
        }
        response = self.client.post('/api/applications/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Application.objects.count(), 1)
        self.assertEqual(Application.objects.first().url, 'https://example.com')
    
    def test_invalid_url(self):
        """Test invalid URL is rejected"""
        data = {
            'url': 'not-a-url',
            'base_url': 'not-a-url'
        }
        response = self.client.post('/api/applications/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_list_applications(self):
        """Test listing applications"""
        Application.objects.create(
            user=self.user,
            url='https://example1.com',
            base_url='https://example1.com'
        )
        Application.objects.create(
            user=self.user,
            url='https://example2.com',
            base_url='https://example2.com'
        )
        
        response = self.client.get('/api/applications/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_login_required(self):
        """Test unauthenticated access is denied"""
        client = APIClient()
        response = client.get('/api/applications/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class ApplicationValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_login_url_without_credentials(self):
        """Test login_url requires username and password"""
        data = {
            'url': 'https://example.com',
            'base_url': 'https://example.com',
            'login_url': 'https://example.com/login'
        }
        response = self.client.post('/api/applications/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Username', str(response.data))