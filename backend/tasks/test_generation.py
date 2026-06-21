import logging
from django.utils import timezone
from celery import shared_task
from django.db import transaction

from core.models import Application, Page, TestCase, CeleryTask
from services.llm_service import LLMService

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="tasks.test_generation.generate_tests")
def generate_tests(self, app_id):
    """
    Celery task that retrieves discovered pages/forms, sends them to the LLM service
    to generate test cases, and stores the test cases in the database, tracking task progress.
    """
    logger.info(f"Starting test generation task for application ID: {app_id}")
    
    # Create task tracking record
    task_id = self.request.id or "dummy_task_id"
    task_record = CeleryTask.objects.create(
        task_id=task_id,
        task_type='test_generation',
        status='progress',
        progress=10,
        result={"status_text": "Initializing test generation..."}
    )
    
    try:
        try:
            app = Application.objects.get(id=app_id)
        except Application.DoesNotExist:
            logger.error(f"Application with ID {app_id} does not exist.")
            task_record.status = 'failed'
            task_record.error = f"Application with ID {app_id} not found."
            task_record.completed_at = timezone.now()
            task_record.save()
            return {"error": f"Application with ID {app_id} not found."}

        # Fetch all pages for this application
        pages = Page.objects.filter(app=app)
        if not pages.exists():
            logger.warning(f"No pages found for application ID {app_id}. Cannot generate tests.")
            task_record.status = 'failed'
            task_record.error = "No pages discovered yet. Run discovery first."
            task_record.completed_at = timezone.now()
            task_record.save()
            return {"error": "No pages discovered yet. Run discovery first."}

        task_record.progress = 30
        task_record.result = {"status_text": "Retrieving discovered pages & compiling prompt..."}
        task_record.save()

        # Construct the input format for LLM Service
        pages_list = []
        for page in pages:
            pages_list.append({
                "url": page.url,
                "title": page.title,
                "forms": page.forms,
                "buttons": page.buttons
            })
            
        pages_data = {
            "pages": pages_list
        }

        # Generate test cases using LLM Service
        task_record.progress = 50
        task_record.result = {"status_text": "Generating test cases using local Ollama AI model..."}
        task_record.save()

        llm_service = LLMService()
        test_cases_data, was_ai = llm_service.generate_test_cases(pages_data)

        if not test_cases_data:
            logger.error("Failed to generate any test cases.")
            task_record.status = 'failed'
            task_record.error = "Failed to generate any test cases."
            task_record.completed_at = timezone.now()
            task_record.save()
            return {"error": "Test case generation failed."}

        task_record.progress = 80
        task_record.result = {"status_text": "Writing generated test cases to database..."}
        task_record.save()

        # Save test cases to database in a transaction
        with transaction.atomic():
            # Delete previous test cases for this app to avoid duplicates
            TestCase.objects.filter(app=app).delete()
            
            # Create new test cases
            for tc in test_cases_data:
                TestCase.objects.create(
                    app=app,
                    title=tc["title"],
                    steps=tc["steps"],
                    expected_result=tc["expected_result"],
                    ai_generated=was_ai
                )
            
            logger.info(f"Saved {len(test_cases_data)} test cases to database.")
            
            task_record.status = 'success'
            task_record.progress = 100
            task_record.result = {
                "status_text": f"Successfully generated {len(test_cases_data)} test cases.",
                "tests_generated": len(test_cases_data),
                "ai_generated": was_ai
            }
            task_record.completed_at = timezone.now()
            task_record.save()
            
    except Exception as e:
        logger.error(f"Failed to save test cases to database: {e}")
        task_record.status = 'failed'
        task_record.error = str(e)
        task_record.completed_at = timezone.now()
        task_record.save()
        return {"error": f"Failed to save test cases: {str(e)}"}

    return {
        "status": "SUCCESS",
        "tests_generated": len(test_cases_data),
        "ai_generated": was_ai
    }
