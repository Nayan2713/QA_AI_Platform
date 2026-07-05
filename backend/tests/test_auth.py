from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework import status
import json

class AuthenticationTests(TestCase):
    def setUp(self):
        # Base URLs
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.refresh_url = '/api/auth/refresh/'
        self.protected_url = '/api/applications/'

        # Setup standard credentials for later tests
        self.username = 'active_tester'
        self.email = 'tester@qaengine.com'
        self.password = 'super_secure_pass123'
        
        # Pre-create a user to test duplicate constraints and login
        self.existing_user = User.objects.create_user(
            username='duplicate_name',
            email='duplicate@qaengine.com',
            password='testpassword123'
        )

    def get_error_data(self, response):
        """Helper to extract validation errors from custom exception handler wrapping"""
        data = response.json()
        if 'detail' in data and isinstance(data['detail'], dict):
            return data['detail']
        return data

    # ==========================
    # REGISTRATION TEST CASES
    # ==========================

    def test_valid_registration(self):
        """1. Valid user registration returning 201 status and JWT tokens"""
        payload = {
            "username": self.username,
            "email": self.email,
            "password": self.password
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], self.username)
        self.assertEqual(data['user']['email'], self.email)
        
        # Verify user is saved in DB and password is secure/hashed
        user = User.objects.get(username=self.username)
        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(user.password.startswith('pbkdf2_sha256$') or user.password.startswith('argon2$'))

    def test_registration_duplicate_username(self):
        """2. Registration fails with 400 when username is taken"""
        payload = {
            "username": 'duplicate_name',
            "email": 'unique_email@qaengine.com',
            "password": 'password123'
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = self.get_error_data(response)
        self.assertIn('username', error_data)

    def test_registration_duplicate_email(self):
        """3. Registration fails with 400 when email is taken"""
        payload = {
            "username": 'unique_username',
            "email": 'duplicate@qaengine.com',
            "password": 'password123'
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = self.get_error_data(response)
        self.assertIn('email', error_data)

    def test_registration_invalid_email(self):
        """4. Registration fails with 400 when email format is invalid"""
        payload = {
            "username": self.username,
            "email": 'invalid_email_format',
            "password": self.password
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = self.get_error_data(response)
        self.assertIn('email', error_data)

    def test_registration_missing_username(self):
        """5. Registration fails with 400 when username is missing"""
        payload = {
            "email": self.email,
            "password": self.password
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = self.get_error_data(response)
        self.assertIn('username', error_data)

    def test_registration_missing_password(self):
        """6. Registration fails with 400 when password is missing"""
        payload = {
            "username": self.username,
            "email": self.email
        }
        response = self.client.post(
            self.register_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = self.get_error_data(response)
        self.assertIn('password', error_data)

    def test_registration_empty_payload(self):
        """7. Registration fails with 400 on empty payload"""
        response = self.client.post(
            self.register_url,
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==========================
    # LOGIN TEST CASES (EMAIL-BASED)
    # ==========================

    def test_valid_login(self):
        """8. Valid login with email returns JWT tokens and user info with 200 status"""
        payload = {
            "email": 'duplicate@qaengine.com',
            "password": 'testpassword123'
        }
        response = self.client.post(
            self.login_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], 'duplicate_name')
        self.assertEqual(data['user']['email'], 'duplicate@qaengine.com')

    def test_invalid_login_wrong_email(self):
        """9. Login fails with 401 on wrong/non-existent email"""
        payload = {
            "email": 'wrong_email@qaengine.com',
            "password": 'testpassword123'
        }
        response = self.client.post(
            self.login_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.json())

    def test_invalid_login_wrong_password(self):
        """10. Login fails with 401 on wrong password"""
        payload = {
            "email": 'duplicate@qaengine.com',
            "password": 'wrong_password_abc'
        }
        response = self.client.post(
            self.login_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_missing_password(self):
        """11. Login fails with 400 when password is missing"""
        payload = {
            "email": 'duplicate@qaengine.com'
        }
        response = self.client.post(
            self.login_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==========================
    # TOKEN REFRESH & PROTECTED APIS
    # ==========================

    def test_token_refresh_lifecycle(self):
        """12. Valid token refresh yields a new access token"""
        # First log in
        login_payload = {
            "email": 'duplicate@qaengine.com',
            "password": 'testpassword123'
        }
        login_response = self.client.post(
            self.login_url,
            data=json.dumps(login_payload),
            content_type='application/json'
        )
        refresh_token = login_response.json()['refresh']

        # Call refresh endpoint
        refresh_payload = {
            "refresh": refresh_token
        }
        response = self.client.post(
            self.refresh_url,
            data=json.dumps(refresh_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.json())

    def test_token_refresh_user_not_exist(self):
        """12b. Refreshing a token for a deleted user returns 401 Unauthorized instead of 500"""
        # First log in
        login_payload = {
            "email": 'duplicate@qaengine.com',
            "password": 'testpassword123'
        }
        login_response = self.client.post(
            self.login_url,
            data=json.dumps(login_payload),
            content_type='application/json'
        )
        refresh_token = login_response.json()['refresh']

        # Delete the user
        User.objects.filter(email='duplicate@qaengine.com').delete()

        # Call refresh endpoint
        refresh_payload = {
            "refresh": refresh_token
        }
        response = self.client.post(
            self.refresh_url,
            data=json.dumps(refresh_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()['detail'], 'No active account found for the given token.')

    def test_protected_endpoint_without_token(self):
        """13. Accessing protected endpoint without token returns 401"""
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_with_valid_token(self):
        """14. Accessing protected endpoint with valid JWT access token succeeds"""
        # First log in
        login_payload = {
            "email": 'duplicate@qaengine.com',
            "password": 'testpassword123'
        }
        login_response = self.client.post(
            self.login_url,
            data=json.dumps(login_payload),
            content_type='application/json'
        )
        access_token = login_response.json()['access']

        # Get protected endpoint with authorization headers
        headers = {
            'HTTP_AUTHORIZATION': f'Bearer {access_token}'
        }
        response = self.client.get(self.protected_url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_protected_endpoint_with_invalid_token(self):
        """15. Accessing protected endpoint with invalid JWT returns 401"""
        headers = {
            'HTTP_AUTHORIZATION': 'Bearer invalid_access_token_token'
        }
        response = self.client.get(self.protected_url, **headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
