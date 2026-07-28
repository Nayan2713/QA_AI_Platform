from celery import shared_task
from django.utils import timezone
import logging

from core.models import CeleryTask, Application, TestCase

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="tasks.bulk_upload.process_bulk_upload", queue="celery")
def process_bulk_upload(self, app_id, file_bytes, filename, model_choice='auto', is_preview=False):
    """
    Runs BulkTestCaseService.process_bulk_file in the background instead of
    blocking the HTTP request. Mirrors the CeleryTask tracking pattern used
    by tasks.discovery.start_discovery.
    """
    task_id = self.request.id or "dummy_task_id"

    task_record, created = CeleryTask.objects.get_or_create(
        task_id=task_id,
        defaults={'task_type': 'bulk_upload', 'status': 'progress', 'progress': 10}
    )
    if not created:
        task_record.status = 'progress'
        task_record.progress = 10
        task_record.save(update_fields=['status', 'progress'])

    try:
        app = Application.objects.get(id=app_id)
    except Application.DoesNotExist:
        task_record.status = 'failed'
        task_record.error = f"Application with ID {app_id} not found."
        task_record.completed_at = timezone.now()
        task_record.save()
        return {"error": f"Application with ID {app_id} not found."}

    task_record.progress = 30
    task_record.save(update_fields=['progress'])

    from services.bulk_test_case_service import BulkTestCaseService
    import io

    file_like = io.BytesIO(file_bytes)

    try:
        result = BulkTestCaseService.process_bulk_file(file_like, filename, app, model_choice=model_choice)
    except ValueError as ve:
        task_record.status = 'failed'
        task_record.error = str(ve)
        task_record.completed_at = timezone.now()
        task_record.save()
        return {"error": str(ve)}
    except Exception as e:
        import traceback
        logger.error(f"Bulk upload parse failed for app {app_id}: {e}\n{traceback.format_exc()}")
        task_record.status = 'failed'
        task_record.error = f"Failed to parse file: {str(e)}"
        task_record.completed_at = timezone.now()
        task_record.save()
        return {"error": f"Failed to parse file: {str(e)}"}

    task_record.progress = 70
    task_record.save(update_fields=['progress'])

    if is_preview:
        task_record.status = 'success'
        task_record.progress = 100
        task_record.result = {
            "status": "preview",
            "filename": filename,
            "columns": result.get("columns", []),
            "format_type": result.get("format_type", ""),
            "truncated": result.get("truncated", False),
            "parse_warning": result.get("parse_warning"),
            "count": result.get("count", 0),
            "test_cases": result.get("test_cases", []),
        }
        task_record.completed_at = timezone.now()
        task_record.save()
        return task_record.result

    objs_to_create = []
    for item in result.get("test_cases", []):
        objs_to_create.append(TestCase(
            app=app,
            title=str(item.get('title', 'Imported Test Case'))[:255],
            category=item.get('category', 'Generic') if item.get('category') in ['Generic', 'Industry Flow', 'Access Control'] else 'Generic',
            expected_result=str(item.get('expected_result', 'Verification successful')),
            steps=item.get('steps', []),
            ai_generated=False,
            generation_context=item.get('generation_context', {})
        ))
    created_cases = TestCase.objects.bulk_create(objs_to_create)

    from core.serializers import TestCaseSerializer

    task_record.status = 'success'
    task_record.progress = 100
    task_record.result = {
        "status": "success",
        "message": f"Successfully imported {len(created_cases)} test cases from {filename}.",
        "created_count": len(created_cases),
        "columns": result.get("columns", []),
        "format_type": result.get("format_type", ""),
        "truncated": result.get("truncated", False),
        "parse_warning": result.get("parse_warning"),
        "test_case_ids": [c.id for c in created_cases],
    }
    task_record.completed_at = timezone.now()
    task_record.save()
    return task_record.result