import os
import time
import logging
import json
import base64
from django.conf import settings
from django.utils import timezone
from browser_use import Agent, Browser, ChatOllama

from config.llm_config import get_llm, estimate_tokens
from core.models import AgentSession, Page, Bug, Application

logger = logging.getLogger(__name__)

class BrowserUseAgent:
    def __init__(self):
        self.llm = get_llm()

    async def log_session(self, application, task_type, status, steps_taken, result_summary, start_time, tokens=0):
        """Helper to create and save an AgentSession record in the DB"""
        duration = time.time() - start_time
        try:
            from asgiref.sync import sync_to_async
            
            # Estimate tokens if not supplied
            if tokens == 0:
                tokens = estimate_tokens(str(steps_taken)) + estimate_tokens(result_summary)

            def save_record():
                return AgentSession.objects.create(
                    application=application,
                    task_type=task_type,
                    status=status,
                    llm_model=getattr(settings, 'OLLAMA_MODEL', 'qwen:7b'),
                    steps_taken=steps_taken,
                    tokens_used=tokens,
                    duration_seconds=duration,
                    result_summary=result_summary
                )
            
            await sync_to_async(save_record)()
        except Exception as err:
            logger.error(f"Failed logging agent session record: {err}")

    async def discover_application(self, url_or_app, credentials=None):
        """
        Explores the target application URL, discovers pages, forms, inputs, and buttons.
        """
        start_time = time.time()
        
        # Support both Application model instance and raw URL string
        if isinstance(url_or_app, str):
            from core.models import Application
            from asgiref.sync import sync_to_async
            def get_or_create():
                app, _ = Application.objects.get_or_create(url=url_or_app, defaults={'user_id': 1})
                return app
            application = await sync_to_async(get_or_create)()
            url = url_or_app
        else:
            application = url_or_app
            url = application.url

        logger.info(f"Agent starting discovery for URL: {url}")
        
        login_clause = ""
        if credentials and application.login_url:
            login_clause = (
                f"First, navigate to the login page at {application.login_url} "
                f"and authenticate using username/email '{credentials.get('username')}' "
                f"and password '{credentials.get('password')}'."
            )

        task = (
            f"Explore the application starting at {url}. {login_clause} "
            f"Navigate through all accessible pages, header menus, and sidebar links. "
            f"For each unique page discovered, collect its URL, page title, and identify all input forms, buttons, "
            f"or dropdown selectors. Audit their structural layouts. "
            f"Return a structured JSON output with a list of pages found, including forms, buttons, and page type tags."
        )

        storage_state_dict = None
        if application.storage_state:
            try:
                storage_state_dict = json.loads(application.storage_state)
            except Exception as e:
                logger.error(f"Failed parsing storage state in BrowserUseAgent: {e}")

        browser = Browser(headless=True, storage_state=storage_state_dict)
        agent = Agent(task=task, llm=self.llm, browser=browser)
        
        steps = []
        status = "completed"
        result_summary = ""
        
        try:
            history = await agent.run()
            result_summary = history.final_result() or "Discovery finished."
            
            # Export updated storage state
            try:
                new_state = browser.export_storage_state()
                if new_state:
                    from asgiref.sync import sync_to_async
                    def save_storage():
                        application.storage_state = json.dumps(new_state)
                        application.save()
                    await sync_to_async(save_storage)()
            except Exception as save_err:
                logger.error(f"Failed exporting storage state after agent discovery: {save_err}")

            # Serialize execution steps history
            for idx, step in enumerate(history.history):
                steps.append({
                    "step": idx + 1,
                    "action": str(step.action) if hasattr(step, 'action') else "action",
                    "result": str(step.result) if hasattr(step, 'result') else "success"
                })
        except Exception as e:
            logger.error(f"BrowserUseAgent discovery failed: {e}")
            status = "failed"
            result_summary = f"Discovery run aborted due to error: {str(e)}"
        finally:
            await browser.close()

        await self.log_session(application, "discovery", status, steps, result_summary, start_time)
        
        # Parse result_summary or return a structured mock if local LLM fails to output valid JSON
        discovered_data = {
            "pages": [],
            "forms": [],
            "workflows": [],
            "apis": [],
            "elements": []
        }
        
        try:
            # Attempt to extract JSON from result_summary
            cleaned = result_summary.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                discovered_data.update(parsed)
        except Exception:
            logger.warning("Could not parse structured JSON from agent discovery result_summary. Returning unstructured log.")
            # Set a default discovered page based on the start_url
            discovered_data["pages"].append({
                "url": url,
                "title": "Discovered Homepage",
                "page_type": "home",
                "elements": {"forms": [], "buttons": []}
            })

        return discovered_data

    async def generate_and_execute_test(self, test_case, url, credentials=None):
        """
        Adapts and executes a test case dynamically using browser-use.
        """
        start_time = time.time()
        application = test_case.app
        logger.info(f"Agent executing test case '{test_case.title}' for URL: {url}")
        
        login_clause = ""
        if credentials and application.login_url:
            login_clause = (
                f"First login at {application.login_url} using "
                f"username '{credentials.get('username')}' and password '{credentials.get('password')}'."
            )

        task = (
            f"Navigate to {url}. {login_clause} "
            f"Execute this scenario step-by-step: {test_case.expected_result}. "
            f"Specifically perform these actions: {json.dumps(test_case.steps)}. "
            f"Assert that the test meets the expected result: '{test_case.expected_result}'. "
            f"If there are modal popups, cookie consent overlays, or unexpected page redirects, resolve them automatically."
        )

        storage_state_dict = None
        if application.storage_state:
            try:
                storage_state_dict = json.loads(application.storage_state)
            except Exception as e:
                logger.error(f"Failed parsing storage state in BrowserUseAgent execution: {e}")

        browser = Browser(headless=True, storage_state=storage_state_dict)
        agent = Agent(task=task, llm=self.llm, browser=browser)
        
        steps = []
        status = "completed"
        result_summary = ""
        screenshot_path = None
        bug_details = None

        try:
            history = await agent.run()
            result_summary = history.final_result() or "Test execution finished."
            
            # Export updated storage state
            try:
                new_state = browser.export_storage_state()
                if new_state:
                    from asgiref.sync import sync_to_async
                    def save_storage():
                        application.storage_state = json.dumps(new_state)
                        application.save()
                    await sync_to_async(save_storage)()
            except Exception as save_err:
                logger.error(f"Failed exporting storage state after agent execution: {save_err}")

            for idx, step in enumerate(history.history):
                steps.append({
                    "step": idx + 1,
                    "action": str(step.action) if hasattr(step, 'action') else "action",
                    "result": str(step.result) if hasattr(step, 'result') else "success"
                })

            # Check if any step failed or if final result states failure
            has_failure = "fail" in result_summary.lower() or "error" in result_summary.lower()
            if has_failure:
                status = "failed"
                # Save screenshot from last step if available
                last_step = history.history[-1] if history.history else None
                if last_step and getattr(last_step, 'screenshot', None):
                    screenshot_path = await self.save_screenshot(last_step.screenshot, application.id)
                    bug_details = {
                        "bug_type": "functional",
                        "severity": "major",
                        "title": f"Agent Test Failure: {test_case.title}",
                        "description": result_summary,
                        "element_selector": None
                    }
        except Exception as e:
            logger.error(f"BrowserUseAgent execution failed: {e}")
            status = "failed"
            result_summary = f"Execution aborted: {str(e)}"
            
            # Attempt to take a failure screenshot
            try:
                # Get current page and save screenshot if possible
                playwright_browser = await browser.get_playwright_browser()
                if playwright_browser.contexts:
                    page = playwright_browser.contexts[0].pages[0]
                    ss_bytes = await page.screenshot(full_page=False)
                    screenshot_path = await self.save_screenshot(base64.b64encode(ss_bytes).decode('utf-8'), application.id)
            except Exception as ss_err:
                logger.error(f"Failed capturing fallback error screenshot: {ss_err}")

            bug_details = {
                "bug_type": "functional",
                "severity": "critical",
                "title": f"Agent Execution Crash: {test_case.title}",
                "description": f"The browser agent crashed during execution: {str(e)}",
                "element_selector": None
            }
        finally:
            await browser.close()

        await self.log_session(application, "test_execution", status, steps, result_summary, start_time)

        return {
            "status": "COMPLETED" if status == "completed" else "FAILED",
            "result": result_summary,
            "screenshot_path": screenshot_path,
            "bug_details": bug_details
        }

    async def detect_bugs(self, url_or_app, credentials=None):
        """
        Audits the target web app, checks for JS console errors, broken elements, or validation issues.
        """
        start_time = time.time()
        
        # Support both Application model instance and raw URL string
        if isinstance(url_or_app, str):
            from core.models import Application
            from asgiref.sync import sync_to_async
            def get_or_create():
                app, _ = Application.objects.get_or_create(url=url_or_app, defaults={'user_id': 1})
                return app
            application = await sync_to_async(get_or_create)()
            url = url_or_app
        else:
            application = url_or_app
            url = application.url

        logger.info(f"Agent auditing application for bugs: {url}")
        
        login_clause = ""
        if credentials and application.login_url:
            login_clause = (
                f"Log in first at {application.login_url} using username '{credentials.get('username')}' "
                f"and password '{credentials.get('password')}'."
            )

        task = (
            f"Explore the website starting at {url}. {login_clause} "
            f"Inspect the homepage and primary subpages. Search for defects such as: "
            f"1. Broken links, console errors, or JS exceptions.\n"
            f"2. Broken styling, missing media icons, overlapping text components.\n"
            f"3. Form validation failure handling (e.g. submit forms empty to trigger errors).\n"
            f"Identify any critical or minor errors. Return a list of all identified bugs in a JSON array format."
        )

        browser = Browser(headless=True)
        agent = Agent(task=task, llm=self.llm, browser=browser)
        
        steps = []
        status = "completed"
        result_summary = ""
        bugs_found = []

        try:
            history = await agent.run()
            result_summary = history.final_result() or "Bug detection finished."
            
            for idx, step in enumerate(history.history):
                steps.append({
                    "step": idx + 1,
                    "action": str(step.action) if hasattr(step, 'action') else "action",
                    "result": str(step.result) if hasattr(step, 'result') else "success"
                })
                
                # Check for individual step errors to log as minor/major bugs
                if step.result and ("error" in str(step.result).lower() or "exception" in str(step.result).lower()):
                    screenshot_file = None
                    if getattr(step, 'screenshot', None):
                        screenshot_file = await self.save_screenshot(step.screenshot, application.id)
                    
                    bugs_found.append({
                        "bug_type": "ui",
                        "severity": "minor",
                        "title": "Browser Step Warning/Error",
                        "description": str(step.result),
                        "screenshot": screenshot_file,
                        "element_selector": None
                    })
        except Exception as e:
            logger.error(f"BrowserUseAgent bug detection failed: {e}")
            status = "failed"
            result_summary = f"Bug audit aborted: {str(e)}"
        finally:
            await browser.close()

        await self.log_session(application, "bug_detection", status, steps, result_summary, start_time)

        # Parse general bugs list from result_summary
        try:
            cleaned = result_summary.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                for b in parsed:
                    bugs_found.append({
                        "bug_type": b.get("bug_type", "functional"),
                        "severity": b.get("severity", "medium"),
                        "title": b.get("title", "Discovered UI/Functional Bug"),
                        "description": b.get("description", "Error observed during crawler audit."),
                        "element_selector": b.get("element_selector"),
                        "screenshot": None
                    })
        except Exception:
            logger.warning("Could not parse structured bugs list from agent result_summary.")

        return bugs_found

    async def execute_workflow_test(self, workflow_description, url, credentials=None):
        """
        Executes a complete multi-step user workflow end-to-end.
        """
        start_time = time.time()
        logger.info(f"Agent executing workflow test: '{workflow_description}'")
        
        # Temporary Application mapping for generic workflow tests
        from asgiref.sync import sync_to_async
        def get_or_create_app():
            app, _ = Application.objects.get_or_create(url=url, defaults={'user_id': 1})
            return app
        application = await sync_to_async(get_or_create_app)()
        
        login_clause = ""
        if credentials and application.login_url:
            login_clause = (
                f"Log in first at {application.login_url} using credentials "
                f"username '{credentials.get('username')}' and password '{credentials.get('password')}'."
            )

        task = (
            f"Go to {url}. {login_clause} "
            f"Execute this workflow: {workflow_description}. "
            f"Perform all intermediate steps, validations, and transitions. "
            f"Return a step-by-step summary detailing the results of the workflow."
        )

        browser = Browser(headless=True)
        agent = Agent(task=task, llm=self.llm, browser=browser)
        
        steps = []
        status = "completed"
        result_summary = ""

        try:
            history = await agent.run()
            result_summary = history.final_result() or "Workflow test finished."
            
            for idx, step in enumerate(history.history):
                steps.append({
                    "step": idx + 1,
                    "action": str(step.action) if hasattr(step, 'action') else "action",
                    "result": str(step.result) if hasattr(step, 'result') else "success"
                })
        except Exception as e:
            logger.error(f"BrowserUseAgent workflow execution failed: {e}")
            status = "failed"
            result_summary = f"Workflow run aborted: {str(e)}"
        finally:
            await browser.close()

        await self.log_session(application, "test_execution", status, steps, result_summary, start_time)

        return {
            "status": "COMPLETED" if status == "completed" else "FAILED",
            "result": result_summary,
            "steps": steps
        }

    async def save_screenshot(self, screenshot_b64, application_id):
        """Saves base64 screenshot string to media/bugs/ folder"""
        try:
            media_path = os.path.join(settings.MEDIA_ROOT, 'bugs')
            os.makedirs(media_path, exist_ok=True)
            
            filename = f"bug_{application_id}_{int(time.time())}.png"
            filepath = os.path.join(media_path, filename)
            
            # Decode and write
            image_data = base64.b64decode(screenshot_b64)
            with open(filepath, 'wb') as f:
                f.write(image_data)
                
            return f"bugs/{filename}"
        except Exception as err:
            logger.error(f"Failed to save agent screenshot: {err}")
            return None

    async def execute_test(self, test_case, url, credentials=None):
        """Wrapper method matching user specification and routing to internal runner"""
        return await self.generate_and_execute_test(test_case, url, credentials)
