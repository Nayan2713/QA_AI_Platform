from django.core.management.base import BaseCommand
from core.models import TestCase

class Command(BaseCommand):
    help = 'Clean up CSRF and token steps from existing test cases'

    def handle(self, *args, **kwargs):
        self.stdout.write("Cleaning up CSRF/token steps from existing test cases...")
        updated_count = 0
        for tc in TestCase.objects.all():
            original_steps = list(tc.steps)
            new_steps = []
            for step in original_steps:
                selector = step.get('selector', '') or ''
                action = step.get('action', '') or ''
                # Skip steps that try to fill hidden csrf/tokens/downloadURL
                if action == 'fill' and ('_token' in selector or 'csrf' in selector or 'downloadURL' in selector):
                    self.stdout.write(f"  Skipping hidden step: {action} {selector} in '{tc.title}'")
                    continue
                new_steps.append(step)
            
            if len(new_steps) != len(original_steps):
                tc.steps = new_steps
                tc.save()
                updated_count += 1
                self.stdout.write(f"Updated TestCase '{tc.title}': removed {len(original_steps) - len(new_steps)} steps.")
        
        self.stdout.write(f"Successfully cleaned up {updated_count} test cases.")
