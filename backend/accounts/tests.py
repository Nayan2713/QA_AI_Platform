from django.test import TestCase

# Create your tests here.
from django.test import TestCase
from django.contrib.auth.models import User

class AuthTest(TestCase):

    def test_register_user(self):

        user = User.objects.create_user(
            username="test",
            password="test123"
        )

        self.assertEqual(
            user.username,
            "test"
        )