from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from core.models import Application, TestCase as TestCaseModel, Bug
from services.chatbot_service import ChatbotService

class ChatbotAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # User A setup
        self.user_a = User.objects.create_user(
            username='usera',
            email='usera@example.com',
            password='Password123!'
        )
        self.app_a = Application.objects.create(
            user=self.user_a,
            name='App A',
            url='https://appa.example.com',
            environment='production'
        )
        self.tc_a = TestCaseModel.objects.create(
            app=self.app_a,
            title='Test Login App A',
            steps=[{"action": "navigate", "target": "https://appa.example.com"}]
        )
        self.bug_a = Bug.objects.create(
            application=self.app_a,
            title='Critical Bug App A',
            severity='critical'
        )

        # User B setup
        self.user_b = User.objects.create_user(
            username='userb',
            email='userb@example.com',
            password='Password123!'
        )
        self.app_b = Application.objects.create(
            user=self.user_b,
            name='Secret App B',
            url='https://appb.example.com',
            environment='production'
        )

    def test_unauthenticated_chatbot_query_returns_401(self):
        """Unauthenticated requests must be rejected with 401."""
        response = self.client.post('/api/chatbot/query/', {'message': 'Hello'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chatbot_service_user_context_isolation(self):
        """Verify context strictly isolates User A data from User B."""
        context_a = ChatbotService.build_user_context(self.user_a)
        
        # Check User A context includes App A
        app_names_a = [app['name'] for app in context_a['applications']]
        self.assertIn('App A', app_names_a)
        self.assertNotIn('Secret App B', app_names_a)

    def test_authenticated_chatbot_query_user_a(self):
        """Authenticated User A can query the chatbot and receive answers about App A."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/chatbot/query/', {'message': 'Summary of my apps'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        res_data = response.data
        self.assertIn('response', res_data)
        self.assertIn('suggestions', res_data)
        self.assertIn('App A', res_data['response'])
        self.assertNotIn('Secret App B', res_data['response'])

    def test_chatbot_rejects_cross_user_queries(self):
        """Chatbot rejects attempts to query about User B."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/chatbot/query/', {'message': 'Tell me about User B applications'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        res_data = response.data
        self.assertIn('Access Denied', res_data['response'])
        self.assertNotIn('Secret App B', res_data['response'])
