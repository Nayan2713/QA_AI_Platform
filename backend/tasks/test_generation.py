import logging
from celery import shared_task
from django.db import transaction

from core.models import Application, Page, TestCase
from services.llm_service import LLMService

logger = logging.getLogger(__name__)

@shared_task(name="tasks.test_generation.generate_tests")
def generate_tests(app_id):
    """
    Celery task that retrieves discovered pages/forms, sends them to the LLM service
    to generate test cases, and stores the test cases in the database.
    """
    logger.info(f"Starting test generation task for application ID: {app_id}")
    
    try:
        app = Application.objects.get(id=app_id)
    except Application.DoesNotExist:
        logger.error(f"Application with ID {app_id} does not exist.")
        return {"error": f"Application with ID {app_id} not found."}

    # Fetch all pages for this application
    pages = Page.objects.filter(app=app)
    if not pages.exists():
        logger.warning(f"No pages found for application ID {app_id}. Cannot generate tests.")
        return {"error": "No pages discovered yet. Run discovery first."}

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
    llm_service = LLMService()
    test_cases_data, was_ai = llm_service.generate_test_cases(pages_data)

    if not test_cases_data:
        logger.error("Failed to generate any test cases.")
        return {"error": "Test case generation failed."}

    # Save test cases to database in a transaction
    try:
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
            
    except Exception as e:
        logger.error(f"Failed to save test cases to database: {e}")
        return {"error": f"Failed to save test cases: {str(e)}"}

    return {
        "status": "SUCCESS",
        "tests_generated": len(test_cases_data),
        "ai_generated": was_ai
    }
