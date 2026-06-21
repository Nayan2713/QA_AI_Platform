from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from urllib.parse import urlparse
from .models import Application, Page, TestCase, TestRun, TestResult, Bug, CeleryTask


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user


class ApplicationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    page_count = serializers.IntegerField(source='pages.count', read_only=True)
    test_case_count = serializers.IntegerField(source='test_cases.count', read_only=True)
    bug_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Application
        fields = (
            'id', 'user', 'url', 'base_url', 'login_url', 
            'username', 'password', 'status', 'discovery_source', 
            'page_count', 'test_case_count', 'bug_count', 'created_at'
        )
        read_only_fields = ('base_url', 'status', 'discovery_source')

    def get_bug_count(self, obj):
        # Count bugs associated with all test runs of this application's test cases
        return Bug.objects.filter(test_run__test_case__app=obj).count()

    def validate(self, attrs):
        url = attrs.get('url')
        if url:
            parsed = urlparse(url)
            attrs['base_url'] = f"{parsed.scheme}://{parsed.netloc}"
        return attrs


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ('id', 'app', 'url', 'title', 'forms', 'buttons', 'created_at')


class TestCaseSerializer(serializers.ModelSerializer):
    steps = serializers.JSONField()
    
    class Meta:
        model = TestCase
        fields = ('id', 'app', 'title', 'steps', 'expected_result', 'ai_generated', 'created_at')
    
    def validate_steps(self, value):
        """Validate test case steps"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Steps must be a list")
        
        if len(value) == 0:
            raise serializers.ValidationError("At least one step required")
        
        # Validate each step
        valid_actions = ['navigate', 'fill', 'click', 'wait', 'assert']
        for i, step in enumerate(value):
            if not isinstance(step, dict):
                raise serializers.ValidationError(f"Step {i} must be an object")
            
            if 'action' not in step:
                raise serializers.ValidationError(f"Step {i} missing 'action'")
            
            if step['action'] not in valid_actions:
                raise serializers.ValidationError(
                    f"Step {i} has invalid action: {step['action']}"
                )
        
        return value


class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = ('id', 'test_run', 'step_number', 'status', 'error', 'screenshot', 'created_at')


class TestRunSerializer(serializers.ModelSerializer):
    test_case_title = serializers.CharField(source='test_case.title', read_only=True)
    app_url = serializers.CharField(source='test_case.app.url', read_only=True)
    results = TestResultSerializer(source='step_results', many=True, read_only=True)

    class Meta:
        model = TestRun
        fields = ('id', 'test_case', 'test_case_title', 'app_url', 'status', 'metadata', 'results', 'bugs_found', 'created_at')


class BugSerializer(serializers.ModelSerializer):
    test_case_title = serializers.CharField(source='test_run.test_case.title', read_only=True)
    app_url = serializers.CharField(source='test_run.test_case.app.url', read_only=True)

    class Meta:
        model = Bug
        fields = ('id', 'test_run', 'test_case_title', 'app_url', 'title', 'description', 'severity', 'created_at')


class BugDetailSerializer(serializers.ModelSerializer):
    test_run = TestRunSerializer(read_only=True)
    
    class Meta:
        model = Bug
        fields = ('id', 'test_run', 'title', 'description', 'severity', 'created_at')


class CeleryTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = CeleryTask
        fields = (
            'id', 'task_id', 'task_type', 'status', 'progress', 
            'result', 'error', 'created_at', 'updated_at', 'completed_at'
        )
