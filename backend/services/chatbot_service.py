import logging
import json
from django.db.models import Count, Q
from core.models import Application, TestCase, TestRun, Bug, APIEndpoint
from core.views import get_user_and_team_user_ids

logger = logging.getLogger(__name__)

class ChatbotService:
    @staticmethod
    def build_user_context(user, app_id=None):
        """
        Builds a comprehensive, user-isolated context summary for the current user.
        Strictly limits data to applications owned by or shared with `user`.
        """
        user_ids = get_user_and_team_user_ids(user)
        apps_qs = Application.objects.filter(user_id__in=user_ids)
        
        if app_id:
            apps_qs = apps_qs.filter(id=app_id)
            
        apps_summary = []
        for app in apps_qs[:10]:  # Limit top 10 apps
            tc_count = TestCase.objects.filter(app=app).count()
            bug_count = Bug.objects.filter(application=app).count()
            api_count = APIEndpoint.objects.filter(application=app).count()
            latest_run = TestRun.objects.filter(test_case__app=app).order_by('-created_at').first()
            
            apps_summary.append({
                "id": app.id,
                "name": getattr(app, 'name', app.url),
                "url": app.url,
                "environment": getattr(app, 'environment', app.status or 'production'),
                "test_cases_count": tc_count,
                "bugs_count": bug_count,
                "api_endpoints_count": api_count,
                "latest_run_status": latest_run.status if latest_run else "No runs"
            })
            
        # Recent test runs across user apps
        recent_runs_qs = TestRun.objects.filter(test_case__app__user_id__in=user_ids).select_related('test_case', 'test_case__app').order_by('-created_at')[:5]
        recent_runs = [
            {
                "run_id": run.id,
                "app": getattr(run.test_case.app, 'name', run.test_case.app.url),
                "test_case": run.test_case.title,
                "status": run.status,
                "bugs_found": run.bugs_found,
                "created_at": run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "N/A"
            }
            for run in recent_runs_qs
        ]
        
        # Bug severity summary
        bugs_qs = Bug.objects.filter(application__user_id__in=user_ids)
        bug_severity = {
            "critical": bugs_qs.filter(severity='critical').count(),
            "high": bugs_qs.filter(severity='high').count(),
            "medium": bugs_qs.filter(severity='medium').count(),
            "low": bugs_qs.filter(severity='low').count(),
            "total": bugs_qs.count()
        }
        
        # Team Access & Members details
        from core.models import TeamMember
        team_qs = TeamMember.objects.filter(
            Q(owner=user) | Q(member_user=user) | Q(email__iexact=getattr(user, 'email', '')),
        ).select_related('owner', 'member_user')
        
        team_members_list = []
        for tm in team_qs:
            team_members_list.append({
                "id": tm.id,
                "email": tm.email,
                "role": tm.role,
                "status": tm.status,
                "is_owner": (tm.owner_id == user.id),
                "owner_username": tm.owner.username,
                "member_username": tm.member_user.username if tm.member_user else None
            })

        # Notifications summary
        from core.models import Notification
        notifs_qs = Notification.objects.filter(user=user).order_by('-created_at')
        unread_count = notifs_qs.filter(is_read=False).count()
        recent_notifs = [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "level": n.level,
                "is_read": n.is_read,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            for n in notifs_qs[:5]
        ]

        return {
            "username": user.username,
            "user_id": user.id,
            "total_applications": len(apps_summary),
            "applications": apps_summary,
            "recent_test_runs": recent_runs,
            "bugs_summary": bug_severity,
            "team_access": {
                "user_email": getattr(user, 'email', ''),
                "team_members_count": len(team_members_list),
                "members": team_members_list
            },
            "notifications_summary": {
                "unread_count": unread_count,
                "recent_notifications": recent_notifs
            }
        }

    def query_assistant(self, user, user_message, app_id=None):
        """
        Queries the LLM with the user's message and application-scoped context.
        Enforces strict domain boundaries and multi-tenant security.
        """
        # Guard against empty queries
        clean_query = (user_message or "").strip()
        if not clean_query:
            return {
                "response": "Please type a message or select a question to ask.",
                "suggestions": ["What are my latest bugs?", "Summary of my apps", "How do I run test cases?"]
            }

        # Check for explicit prompt injections / cross-user query attempts in the message
        lower_msg = clean_query.lower()
        if any(term in lower_msg for term in ["user b", "other user", "other users", "another user", "all users' data", "admin passwords"]):
            return {
                "response": "Access Denied: I am strictly restricted to accessing and discussing applications and QA data belonging to your account.",
                "suggestions": ["Summary of my apps", "What are my latest bugs?", "How do I run test cases?"]
            }

        # Build context strictly scoped to user
        context_data = self.build_user_context(user, app_id=app_id)
        context_str = json.dumps(context_data, indent=2)

        system_prompt = f"""You are the QA AI Assistant, a specialized AI helper for the QA AI Platform.

YOUR PURPOSE:
Assist the authenticated user (Username: {user.username}) in analyzing test suites, running test cases, reviewing bugs, tracking application health, and navigating the QA platform.

STRICT OPERATIONAL RULES:
1. DOMAIN SCOPE: Answer ONLY questions related to quality assurance, testing, application metrics, bugs, test runs, and how to use this QA platform.
   If the query is clearly unrelated to QA or this platform (e.g. general trivia, cooking recipes, random coding outside QA), politely decline:
   "I am specialized strictly as your QA AI Assistant. I can only answer questions regarding your QA applications, test suites, test run results, bugs, and platform usage."

2. USER PRIVACY & MULTI-TENANCY ISOLATION (CRITICAL SECURITY REQUIREMENT):
   - You ONLY have access to the data of the current authenticated user ({user.username}, ID: {user.id}).
   - Under NO circumstances reveal, search for, or speculate about any other user's data or tenant accounts ("User B").
   - If asked about other users, respond: "Access Denied: I can only access and discuss applications and QA data belonging to your account."

3. CONCISE & HELPFUL FORMAT:
   - Provide direct, concise, formatted answers (using markdown bullets, bolding, and numbers).
   - If the user asks how to perform an action (e.g., run tests, discover endpoints, create apps), give step-by-step instructions for the platform.

AUTHENTICATED USER QA CONTEXT:
```json
{context_str}
```

USER QUERY: {clean_query}
"""

        try:
            from services.llm_service import LLMService
            from config.llm_config import get_llm, llm_predict
            
            # Attempt LLM call
            llm = get_llm()
            response_text = llm_predict(llm, system_prompt)
            
            if not response_text or not response_text.strip():
                response_text = self._fallback_rule_based_response(clean_query, context_data)

        except Exception as err:
            logger.warning(f"LLM call failed for chatbot query: {err}. Falling back to context generator.")
            response_text = self._fallback_rule_based_response(clean_query, context_data)

        # Generate helpful quick suggestions based on current state
        suggestions = [
            "Summary of my apps",
            "What are my latest bugs?",
            "How do I run test cases?",
            "Show recent test runs"
        ]

        return {
            "response": response_text.strip(),
            "suggestions": suggestions
        }

    def _fallback_rule_based_response(self, query, context):
        """
        Deterministic, fast fallback response if LLM port is offline or unreachable.
        """
        q = query.lower()
        if "app" in q or "application" in q:
            apps = context.get("applications", [])
            if not apps:
                return "You currently have 0 applications registered in your workspace. Click **Add Application** on the dashboard to register a web app and begin scanning."
            app_list = "\n".join([f"- **{a['name']}** ({a['url']}): {a['test_cases_count']} test cases, {a['bugs_count']} bugs logged." for a in apps])
            return f"Here is a summary of your applications ({len(apps)} total):\n\n{app_list}"
        
        elif "bug" in q or "defect" in q or "issue" in q:
            bugs = context.get("bugs_summary", {})
            return (
                f"### Bug Summary\n"
                f"- **Total Bugs:** {bugs.get('total', 0)}\n"
                f"- **Critical:** {bugs.get('critical', 0)}\n"
                f"- **High:** {bugs.get('high', 0)}\n"
                f"- **Medium:** {bugs.get('medium', 0)}\n"
                f"- **Low:** {bugs.get('low', 0)}\n\n"
                f"Head over to the **Bugs** tab to inspect full reproduction steps and error tracebacks!"
            )
        
        elif "run" in q or "test run" in q or "execution" in q:
            runs = context.get("recent_test_runs", [])
            if not runs:
                return "No test runs have been executed yet. You can trigger runs from your **Applications** detail page."
            run_list = "\n".join([f"- **Run #{r['run_id']}** on *{r['app']}*: Status `{r['status']}` ({r['bugs_found']} bugs found)" for r in runs])
            return f"### Recent Test Runs\n\n{run_list}"
        
        elif "team" in q or "member" in q or "access" in q or "role" in q:
            team_data = context.get("team_access", {})
            members = team_data.get("members", [])
            if not members:
                return "You currently have no active team members attached to your account. You can invite team members with roles (Admin, Member, Viewer) from the **Team Management** panel on your dashboard."
            
            member_lines = []
            for m in members:
                status_str = f"({m['status']})" if m.get('status') else ""
                owner_tag = " [Team Owner]" if m.get('is_owner') else ""
                member_lines.append(f"- **{m['email']}** - Role: `{m['role']}` {status_str}{owner_tag}")
            
            return f"### Team Access & Members ({len(members)} total):\n" + "\n".join(member_lines)

        elif "notification" in q or "alert" in q or "notice" in q:
            notif_data = context.get("notifications_summary", {})
            recent = notif_data.get("recent_notifications", [])
            unread = notif_data.get("unread_count", 0)
            if not recent:
                return "You have 0 notifications right now. Notifications automatically pop up here when scans or test runs complete! You can delete individual items or click **Clear all** in your header notification dropdown at any time."
            
            lines = [f"- **[{n['level'].upper()}] {n['title']}**: {n['message']} ({n['created_at']})" for n in recent]
            return f"### Notifications ({unread} unread, {len(recent)} recent):\n" + "\n".join(lines) + "\n\n*Tip: Click the 🗑️ icon next to any item in your top header 🔔 menu to delete it, or click **Clear all** to remove all notifications.*"

        elif "how to" in q or "help" in q or "run test" in q:
            return (
                "### How to use QA AI Platform:\n"
                "1. **Add Application**: Click **Add App** and input your website URL.\n"
                "2. **Discover & Scan**: Run discovery to discover pages and API endpoints.\n"
                "3. **Generate Tests**: Generate AI or standard Playwright test cases.\n"
                "4. **Execute**: Run test cases in headless browsers to identify bugs automatically!"
            )
        
        else:
            return (
                f"I am your **QA AI Assistant**. You currently have {context['total_applications']} application(s) and {context['bugs_summary']['total']} logged bug(s).\n\n"
                "You can ask me about:\n"
                "- Your application summaries & health\n"
                "- Logged bugs and error breakdowns\n"
                "- Test execution statuses\n"
                "- How to perform QA scans and run test suites"
            )
