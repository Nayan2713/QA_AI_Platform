from django.core.management.base import BaseCommand
from core.models import TestCase, Bug, TestRun

class Command(BaseCommand):
    help = 'Deduplicate bugs by keeping only the ones from the latest run of each test case'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting DB deduplication of bugs...")
        for tc in TestCase.objects.all():
            runs = TestRun.objects.filter(test_case=tc).order_by('-created_at')
            if runs.exists():
                latest_run = runs[0]
                deleted_count, _ = Bug.objects.filter(test_run__test_case=tc).exclude(test_run=latest_run).delete()
                if deleted_count > 0:
                    self.stdout.write(f"Deleted {deleted_count} historical duplicate bugs for TestCase '{tc.title}' (kept run ID {latest_run.id})")
        self.stdout.write("Deduplication complete!")
