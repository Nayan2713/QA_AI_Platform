from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from urllib.parse import urlparse
from .models import Application, Page, TestCase, TestRun, TestResult, Bug, CeleryTask, APIEndpoint, AgentSession


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


class ApplicationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    page_count = serializers.IntegerField(source='pages.count', read_only=True)
    api_count = serializers.IntegerField(source='api_endpoints.count', read_only=True)
    test_case_count = serializers.IntegerField(source='test_cases.count', read_only=True)
    bug_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Application
        fields = (
            'id', 'user', 'url', 'base_url', 'login_url', 
            'username', 'password', 'status', 'discovery_source', 
            'login_status', 'storage_state', 'login_error', 'industry', 
            'use_llm_in_crawl', 'page_count', 'api_count', 'test_case_count', 'bug_count', 'created_at'
        )
        read_only_fields = ('base_url', 'status', 'discovery_source', 'login_status', 'storage_state', 'login_error')

    def get_bug_count(self, obj):
        from django.db.models import Q
        return Bug.objects.filter(
            Q(test_run__test_case__app=obj) | Q(application=obj)
        ).values('title', 'severity').distinct().count()


    def validate(self, attrs):
        url = attrs.get('url')
        if url:
            from django.db.models import Q
            # Normalize URL by removing trailing slash
            normalized_url = url.rstrip('/')
            parsed = urlparse(normalized_url)
            attrs['base_url'] = f"{parsed.scheme}://{parsed.netloc}"
            
            # Check if this user has already registered this URL (handling trailing slashes too)
            request = self.context.get('request')
            if request and request.user:
                user = request.user
                exists = Application.objects.filter(user=user).filter(
                    Q(url=normalized_url) | Q(url=normalized_url + '/')
                )
                if self.instance:
                    exists = exists.exclude(id=self.instance.id)
                if exists.exists():
                    raise serializers.ValidationError({"url": "You have already registered this application URL."})

        # Validate that login credentials are provided if login_url is specified
        login_url = attrs.get('login_url', getattr(self.instance, 'login_url', None))
        username = attrs.get('username', getattr(self.instance, 'username', None))
        password = attrs.get('password', getattr(self.instance, 'password', None))
        if login_url and (not username or not password):
            raise serializers.ValidationError({
                "username": "Username and password are required if login URL is specified.",
                "password": "Username and password are required if login URL is specified."
            })
            
        return attrs


class ApplicationListSerializer(ApplicationSerializer):
    class Meta:
        model = Application
        fields = (
            'id', 'user', 'url', 'base_url', 'login_url', 
            'username', 'status', 'discovery_source', 
            'login_status', 'login_error', 'industry', 
            'use_llm_in_crawl', 'page_count', 
            'api_count', 'test_case_count', 'bug_count', 'created_at'
        )
        read_only_fields = ('base_url', 'status', 'discovery_source', 'login_status', 'login_error')


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ('id', 'app', 'url', 'title', 'forms', 'buttons', 'page_type', 'elements', 'workflows', 'accessibility_roles', 'created_at')



class TestCaseSerializer(serializers.ModelSerializer):
    steps = serializers.JSONField()
    model_used = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TestCase
        fields = ('id', 'app', 'title', 'category', 'steps', 'expected_result', 'ai_generated', 'validation_status', 'model_used', 'generation_context', 'created_at')
        read_only_fields = ()

    def get_model_used(self, obj):
        if obj.generation_context and isinstance(obj.generation_context, dict):
            return obj.generation_context.get("model_used")
        return None

    def validate_app(self, value):
        """Ensure the app belongs to the requesting user."""
        request = self.context.get('request')
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("You do not own this application.")
        return value

    def validate_steps(self, value):
        """Validate test case steps, including action-specific required fields."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Steps must be a list")

        if len(value) == 0:
            raise serializers.ValidationError("At least one step required")

        valid_actions = ['navigate', 'fill', 'click', 'wait', 'assert', 'hover', 'scroll', 'select', 'screenshot']
        # Which field each action requires
        requires = {
            'navigate': 'target',
            'fill': 'selector',
            'click': 'selector',
            'hover': 'selector',
            'select': 'selector',
            'assert': 'value',
        }

        for i, step in enumerate(value):
            if not isinstance(step, dict):
                raise serializers.ValidationError(f"Step {i + 1} must be an object")

            action = step.get('action')
            if not action:
                raise serializers.ValidationError(f"Step {i + 1} is missing 'action'")

            if action not in valid_actions:
                raise serializers.ValidationError(
                    f"Step {i + 1} has invalid action '{action}'. "
                    f"Allowed: {', '.join(valid_actions)}"
                )

            required_field = requires.get(action)
            if required_field and not str(step.get(required_field, '')).strip():
                raise serializers.ValidationError(
                    f"Step {i + 1} ('{action}') requires a non-empty '{required_field}'."
                )

        return value

        
class TestCaseListSerializer(serializers.ModelSerializer):
    steps = serializers.JSONField()
    model_used = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = TestCase
        fields = ('id', 'app', 'title', 'category', 'steps', 'expected_result', 'ai_generated', 'validation_status', 'model_used', 'created_at')

    def get_model_used(self, obj):
        if hasattr(obj, 'model_used_annotated'):
            return obj.model_used_annotated
        if obj.generation_context and isinstance(obj.generation_context, dict):
            return obj.generation_context.get("model_used")
        return None


class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = ('id', 'test_run', 'step_number', 'status', 'error', 'screenshot', 'created_at')


class TestResultListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = ('id', 'test_run', 'step_number', 'status', 'error', 'created_at')


class TestRunSerializer(serializers.ModelSerializer):
    test_case_title = serializers.CharField(source='test_case.title', read_only=True)
    app_url = serializers.CharField(source='test_case.app.url', read_only=True)
    results = TestResultSerializer(source='step_results', many=True, read_only=True)

    class Meta:
        model = TestRun
        fields = ('id', 'test_case', 'test_case_title', 'app_url', 'status', 'metadata', 'results', 'bugs_found', 'created_at')


class TestRunListSerializer(serializers.ModelSerializer):
    test_case_title = serializers.CharField(source='test_case.title', read_only=True)
    app_url = serializers.CharField(source='test_case.app.url', read_only=True)

    class Meta:
        model = TestRun
        fields = ('id', 'test_case', 'test_case_title', 'app_url', 'status', 'bugs_found', 'created_at')


class APIEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIEndpoint
        fields = ('id', 'application', 'method', 'url_pattern', 'request_schema', 'response_schema', 'auth_type', 'created_at', 'updated_at')


class BugSerializer(serializers.ModelSerializer):
    test_case_title = serializers.SerializerMethodField(read_only=True)
    test_case_id = serializers.SerializerMethodField(read_only=True)
    app_url = serializers.SerializerMethodField(read_only=True)
    app_id = serializers.SerializerMethodField(read_only=True)
    test_case_steps = serializers.SerializerMethodField(read_only=True)
    test_run_results = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bug
        fields = (
            'id', 'application', 'test_run', 'test_case_id', 'app_id', 'test_case_title', 
            'app_url', 'title', 'description', 'severity', 'api_endpoint', 
            'test_case_steps', 'test_run_results', 'bug_type', 'steps_to_reproduce',
            'screenshot', 'element_selector', 'status', 'created_at'
        )

    def get_test_case_title(self, obj):
        return obj.test_run.test_case.title if obj.test_run and obj.test_run.test_case else None
        
    def get_test_case_id(self, obj):
        return obj.test_run.test_case.id if obj.test_run and obj.test_run.test_case else None
        
    def get_app_url(self, obj):
        if obj.test_run and obj.test_run.test_case and obj.test_run.test_case.app:
            return obj.test_run.test_case.app.url
        return obj.application.url if obj.application else None
        
    def get_app_id(self, obj):
        if obj.test_run and obj.test_run.test_case and obj.test_run.test_case.app:
            return obj.test_run.test_case.app.id
        return obj.application.id if obj.application else None
        
    def get_test_case_steps(self, obj):
        return obj.test_run.test_case.steps if obj.test_run and obj.test_run.test_case else []
        
    def get_test_run_results(self, obj):
        if obj.test_run and hasattr(obj.test_run, '_prefetched_objects_cache') and 'step_results' in obj.test_run._prefetched_objects_cache:
            return TestResultListSerializer(obj.test_run.step_results.all(), many=True).data
        return []


class BugDetailSerializer(serializers.ModelSerializer):
    test_run = TestRunSerializer(read_only=True)
    api_endpoint_detail = APIEndpointSerializer(source='api_endpoint', read_only=True)
    
    class Meta:
        model = Bug
        fields = (
            'id', 'application', 'test_run', 'title', 'description', 'severity', 
            'api_endpoint', 'api_endpoint_detail', 'bug_type', 'steps_to_reproduce', 
            'screenshot', 'element_selector', 'status', 'created_at'
        )


class CeleryTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = CeleryTask
        fields = (
            'id', 'app', 'task_id', 'task_type', 'status', 'progress', 
            'result', 'error', 'created_at', 'updated_at', 'completed_at'
        )

class AgentSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentSession
        fields = '__all__'
