import logging
import threading
from django.utils import timezone
from celery import shared_task
from django.db import transaction

from core.models import Application, Page, TestCase, CeleryTask
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


# FIX: use the same run_in_thread helper used by execution.py and discovery.py
# to avoid SynchronousOnlyOperation errors and DB connection leaks inside Celery.
def run_in_thread(func, *args, **kwargs):
    """
    Runs a function in a separate thread to bypass Django's
    SynchronousOnlyOperation check.  Closes the DB connection afterwards
    to prevent connection leaks.
    """
    res = []
    err = []

    def target():
        from django.db import connection
        try:
            result = func(*args, **kwargs)
            # FIX: use a sentinel so None-returning functions don't leave res empty
            res.append(result)
        except Exception as e:
            err.append(e)
        finally:
            connection.close()

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    if err:
        raise err[0]
    # res[0] may legitimately be None for save()/delete() calls — that's fine
    return res[0] if res else None


@shared_task(bind=True, name="tasks.test_generation.generate_tests")
def generate_tests(self, app_id):
    """
    Celery task that retrieves discovered pages/forms, sends them to the LLM
    service to generate test cases, and stores them in the database.
    """
    logger.info(f"Starting test generation task for application ID: {app_id}")

    task_id = self.request.id or "dummy_task_id"

    def get_or_create_task():
        obj, created = CeleryTask.objects.get_or_create(
            task_id=task_id,
            defaults={
                'task_type': 'test_generation',
                'status': 'progress',
                'progress': 10,
                'result': {"status_text": "Initializing test generation..."}
            }
        )
        if not created:
            obj.status = 'progress'
            obj.progress = 10
            obj.result = {"status_text": "Initializing test generation..."}
            obj.save()
        return obj

    task_record = run_in_thread(get_or_create_task)

    try:
        try:
            app = run_in_thread(Application.objects.get, id=app_id)
        except Application.DoesNotExist:
            logger.error(f"Application with ID {app_id} does not exist.")
            def mark_missing():
                task_record.status = 'failed'
                task_record.error = f"Application with ID {app_id} not found."
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(mark_missing)
            return {"error": f"Application with ID {app_id} not found."}

        def get_pages():
            return list(Page.objects.filter(app=app))

        pages = run_in_thread(get_pages)

        if not pages:
            logger.warning(f"No pages found for application ID {app_id}.")
            def mark_no_pages():
                task_record.status = 'failed'
                task_record.error = "No pages discovered yet. Run discovery first."
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(mark_no_pages)
            return {"error": "No pages discovered yet. Run discovery first."}

        def update_progress_30():
            task_record.progress = 30
            task_record.result = {"status_text": "Retrieving discovered pages & compiling prompt..."}
            task_record.save()
        run_in_thread(update_progress_30)

        pages_list = [
            {"url": p.url, "title": p.title, "forms": p.forms, "buttons": p.buttons}
            for p in pages
        ]

        def get_api_endpoints():
            from core.models import APIEndpoint
            return list(APIEndpoint.objects.filter(application=app))

        api_endpoints = run_in_thread(get_api_endpoints)
        api_list = [
            {
                "method": api.method,
                "url_pattern": api.url_pattern,
                "request_schema": api.request_schema,
                "response_schema": api.response_schema,
                "auth_type": api.auth_type,
            }
            for api in api_endpoints
        ]

        pages_data = {"pages": pages_list, "api_endpoints": api_list}

        def update_progress_50():
            task_record.progress = 50
            task_record.result = {"status_text": "Generating test cases using local Ollama AI model..."}
            task_record.save()
        run_in_thread(update_progress_50)

        llm_service = LLMService()
        test_cases_data, was_ai = llm_service.generate_test_cases(pages_data)

        if not test_cases_data:
            logger.error("Failed to generate any test cases.")
            def mark_gen_failed():
                task_record.status = 'failed'
                task_record.error = "Failed to generate any test cases."
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(mark_gen_failed)
            return {"error": "Test case generation failed."}

        def update_progress_80():
            task_record.progress = 80
            task_record.result = {"status_text": "Writing generated test cases to database..."}
            task_record.save()
        run_in_thread(update_progress_80)

        def save_test_cases():
            with transaction.atomic():
                TestCase.objects.filter(app=app).delete()
                for tc in test_cases_data:
                    TestCase.objects.create(
                        app=app,
                        title=tc["title"],
                        steps=tc["steps"],
                        expected_result=tc["expected_result"],
                        ai_generated=was_ai,
                    )
                logger.info(f"Saved {len(test_cases_data)} test cases to database.")
                task_record.status = 'success'
                task_record.progress = 100
                task_record.result = {
                    "status_text": f"Successfully generated {len(test_cases_data)} test cases.",
                    "tests_generated": len(test_cases_data),
                    "ai_generated": was_ai,
                }
                task_record.completed_at = timezone.now()
                task_record.save()

        run_in_thread(save_test_cases)

    except Exception as e:
        logger.error(f"Failed to save test cases to database: {e}")
        def mark_error():
            task_record.status = 'failed'
            task_record.error = str(e)
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(mark_error)
        return {"error": f"Failed to save test cases: {str(e)}"}

    return {
        "status": "SUCCESS",
        "tests_generated": len(test_cases_data),
        "ai_generated": was_ai,
    }



# import logging
# from django.utils import timezone
# from celery import shared_task
# from django.db import transaction

# from core.models import Application, Page, TestCase, CeleryTask
# from services.llm_service import LLMService

# logger = logging.getLogger(__name__)

# @shared_task(bind=True, name="tasks.test_generation.generate_tests")
# def generate_tests(self, app_id):
#     """
#     Celery task that retrieves discovered pages/forms, sends them to the LLM service
#     to generate test cases, and stores the test cases in the database, tracking task progress.
#     """
#     logger.info(f"Starting test generation task for application ID: {app_id}")
    
#     # Create/update task tracking record
#     task_id = self.request.id or "dummy_task_id"
#     task_record, created = CeleryTask.objects.get_or_create(
#         task_id=task_id,
#         defaults={
#             'task_type': 'test_generation',
#             'status': 'progress',
#             'progress': 10,
#             'result': {"status_text": "Initializing test generation..."}
#         }
#     )
#     if not created:
#         task_record.status = 'progress'
#         task_record.progress = 10
#         task_record.result = {"status_text": "Initializing test generation..."}
#         task_record.save()
    
#     try:
#         try:
#             app = Application.objects.get(id=app_id)
#         except Application.DoesNotExist:
#             logger.error(f"Application with ID {app_id} does not exist.")
#             task_record.status = 'failed'
#             task_record.error = f"Application with ID {app_id} not found."
#             task_record.completed_at = timezone.now()
#             task_record.save()
#             return {"error": f"Application with ID {app_id} not found."}

#         # Fetch all pages for this application
#         pages = Page.objects.filter(app=app)
#         if not pages.exists():
#             logger.warning(f"No pages found for application ID {app_id}. Cannot generate tests.")
#             task_record.status = 'failed'
#             task_record.error = "No pages discovered yet. Run discovery first."
#             task_record.completed_at = timezone.now()
#             task_record.save()
#             return {"error": "No pages discovered yet. Run discovery first."}

#         task_record.progress = 30
#         task_record.result = {"status_text": "Retrieving discovered pages & compiling prompt..."}
#         task_record.save()

#         # Construct the input format for LLM Service
#         pages_list = []
#         for page in pages:
#             pages_list.append({
#                 "url": page.url,
#                 "title": page.title,
#                 "forms": page.forms,
#                 "buttons": page.buttons
#             })
            
#         # Fetch API endpoints cataloged for the application
#         from core.models import APIEndpoint
#         api_endpoints = APIEndpoint.objects.filter(application=app)
#         api_list = []
#         for api in api_endpoints:
#             api_list.append({
#                 "method": api.method,
#                 "url_pattern": api.url_pattern,
#                 "request_schema": api.request_schema,
#                 "response_schema": api.response_schema,
#                 "auth_type": api.auth_type
#             })
            
#         pages_data = {
#             "pages": pages_list,
#             "api_endpoints": api_list
#         }

#         # Generate test cases using LLM Service
#         task_record.progress = 50
#         task_record.result = {"status_text": "Generating test cases using local Ollama AI model..."}
#         task_record.save()

#         llm_service = LLMService()
#         test_cases_data, was_ai = llm_service.generate_test_cases(pages_data)

#         if not test_cases_data:
#             logger.error("Failed to generate any test cases.")
#             task_record.status = 'failed'
#             task_record.error = "Failed to generate any test cases."
#             task_record.completed_at = timezone.now()
#             task_record.save()
#             return {"error": "Test case generation failed."}

#         task_record.progress = 80
#         task_record.result = {"status_text": "Writing generated test cases to database..."}
#         task_record.save()

#         # Save test cases to database in a transaction
#         with transaction.atomic():
#             # Delete previous test cases for this app to avoid duplicates
#             TestCase.objects.filter(app=app).delete()
            
#             # Create new test cases
#             for tc in test_cases_data:
#                 TestCase.objects.create(
#                     app=app,
#                     title=tc["title"],
#                     steps=tc["steps"],
#                     expected_result=tc["expected_result"],
#                     ai_generated=was_ai
#                 )
            
#             logger.info(f"Saved {len(test_cases_data)} test cases to database.")
            
#             task_record.status = 'success'
#             task_record.progress = 100
#             task_record.result = {
#                 "status_text": f"Successfully generated {len(test_cases_data)} test cases.",
#                 "tests_generated": len(test_cases_data),
#                 "ai_generated": was_ai
#             }
#             task_record.completed_at = timezone.now()
#             task_record.save()
            
#     except Exception as e:
#         logger.error(f"Failed to save test cases to database: {e}")
#         task_record.status = 'failed'
#         task_record.error = str(e)
#         task_record.completed_at = timezone.now()
#         task_record.save()
#         return {"error": f"Failed to save test cases: {str(e)}"}

#     return {
#         "status": "SUCCESS",
#         "tests_generated": len(test_cases_data),
#         "ai_generated": was_ai
#     }
