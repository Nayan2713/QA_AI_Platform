from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import (
    Application, Page, TestCase, TestRun, TestResult, APIEndpoint,
    Bug, AgentSession, CeleryTask, TestValidation, CoverageReport,
    FlakinessReport, BugValidation, QualityMetrics
)

# ----------------------------------------------------------------------
# Inlines for User Admin
# ----------------------------------------------------------------------

class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0
    fields = ('url', 'base_url', 'status', 'login_status', 'industry', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True

# Re-register UserAdmin to display Applications registered by each user
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    inlines = [ApplicationInline]
    list_display = BaseUserAdmin.list_display + ('registered_applications_count',)

    def registered_applications_count(self, obj):
        return obj.applications.count()
    registered_applications_count.short_description = 'Apps Registered'

# ----------------------------------------------------------------------
# Inlines for Application Admin
# ----------------------------------------------------------------------

class PageInline(admin.TabularInline):
    model = Page
    extra = 0
    fields = ('url', 'title', 'page_type')
    readonly_fields = ('url', 'title', 'page_type')
    show_change_link = True
    can_delete = False

class TestCaseInline(admin.TabularInline):
    model = TestCase
    extra = 0
    fields = ('title', 'category', 'validation_status', 'ai_generated', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True

class BugInline(admin.TabularInline):
    model = Bug
    extra = 0
    fields = ('title', 'severity', 'status', 'bug_type', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True

class CeleryTaskInline(admin.TabularInline):
    model = CeleryTask
    extra = 0
    fields = ('task_type', 'task_id', 'status', 'progress', 'created_at')
    readonly_fields = ('task_id', 'task_type', 'status', 'progress', 'created_at')
    show_change_link = True
    can_delete = False

class QualityMetricsInline(admin.StackedInline):
    model = QualityMetrics
    extra = 0
    fields = ('grade', 'overall_score', 'coverage_score', 'reliability_score', 'accuracy_score', 'relevance_score', 'last_updated')
    readonly_fields = ('last_updated',)

# ----------------------------------------------------------------------
# Application Admin
# ----------------------------------------------------------------------

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'url',
        'registered_by',
        'user_email',
        'status',
        'login_status',
        'industry',
        'discovery_source',
        'created_at',
    )
    list_filter = ('status', 'login_status', 'discovery_source', 'industry', 'created_at', 'user')
    search_fields = ('url', 'base_url', 'login_url', 'username', 'user__username', 'user__email', 'industry')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'password_masked', 'storage_state_preview')
    inlines = [PageInline, TestCaseInline, BugInline, QualityMetricsInline, CeleryTaskInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('url', 'base_url', 'user', 'industry', 'created_at')
        }),
        ('Authentication & Login Details', {
            'fields': ('login_url', 'username', 'password_masked', 'login_status', 'login_error', 'storage_state_preview')
        }),
        ('Crawl & Execution Config', {
            'fields': ('status', 'discovery_source', 'use_llm_in_crawl')
        }),
    )

    def registered_by(self, obj):
        if obj.user:
            return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.user.id, obj.user.username)
        return "-"
    registered_by.short_description = 'Registered By (User)'
    registered_by.admin_order_field = 'user__username'

    def user_email(self, obj):
        return obj.user.email if obj.user else "-"
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'

    def password_masked(self, obj):
        if obj.password:
            return "•••••••• (Encrypted)"
        return "Not Set"
    password_masked.short_description = 'Password (Encrypted at rest)'

    def storage_state_preview(self, obj):
        if obj.storage_state:
            return f"Session state present ({len(obj.storage_state)} bytes)"
        return "No stored session state"
    storage_state_preview.short_description = 'Storage State'

# ----------------------------------------------------------------------
# Other Model Admins
# ----------------------------------------------------------------------

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'url', 'app', 'page_type')
    list_filter = ('page_type', 'app')
    search_fields = ('url', 'title', 'app__url')

@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'app', 'category', 'validation_status', 'ai_generated', 'created_at')
    list_filter = ('validation_status', 'ai_generated', 'category', 'app')
    search_fields = ('title', 'expected_result', 'app__url')

@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'test_case', 'status', 'bugs_found', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('test_case__title',)

@admin.register(Bug)
class BugAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'application', 'severity', 'status', 'bug_type', 'created_at')
    list_filter = ('severity', 'status', 'bug_type', 'application')
    search_fields = ('title', 'description', 'application__url')

@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'application', 'task_type', 'status', 'llm_model', 'tokens_used', 'duration_seconds', 'created_at')
    list_filter = ('task_type', 'status', 'llm_model', 'application')
    search_fields = ('application__url', 'task_type')

@admin.register(CeleryTask)
class CeleryTaskAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'app', 'task_type', 'status', 'progress', 'created_at')
    list_filter = ('status', 'task_type', 'app')
    search_fields = ('task_id', 'task_type', 'app__url')

@admin.register(QualityMetrics)
class QualityMetricsAdmin(admin.ModelAdmin):
    list_display = ('application', 'grade', 'overall_score', 'coverage_score', 'reliability_score', 'accuracy_score', 'relevance_score', 'last_updated')
    list_filter = ('grade', 'last_updated')
    search_fields = ('application__url',)

@admin.register(APIEndpoint)
class APIEndpointAdmin(admin.ModelAdmin):
    list_display = ('id', 'method', 'url_pattern', 'application', 'auth_type', 'created_at')
    list_filter = ('method', 'auth_type', 'application')
    search_fields = ('url_pattern', 'application__url')
