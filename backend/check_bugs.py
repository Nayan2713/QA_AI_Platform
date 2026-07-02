from core.models import Bug, TestResult
import os
from django.conf import settings

print(f"MEDIA_ROOT = {settings.MEDIA_ROOT}")
print(f"MEDIA_URL  = {settings.MEDIA_URL}")
print()

# Check recent bugs with screenshots
print("=== Recent Bugs with screenshot field ===")
for b in Bug.objects.exclude(screenshot='').exclude(screenshot=None).order_by('-id')[:10]:
    ss_val = str(b.screenshot)
    full_path = os.path.join(settings.MEDIA_ROOT, ss_val)
    exists = os.path.exists(full_path)
    print(f"  Bug #{b.id}: screenshot='{ss_val}' | file_exists={exists} | full_path={full_path}")

print()
print("=== Recent FAILED TestResults with screenshot ===")
for r in TestResult.objects.filter(status='FAILED').exclude(screenshot=None).exclude(screenshot='').order_by('-id')[:5]:
    ss_val = str(r.screenshot)
    is_b64 = len(ss_val) > 200
    print(f"  Result #{r.id}: is_base64={is_b64} | len={len(ss_val)} | preview={ss_val[:80]}")

print()
print("=== Check media/bugs directory ===")
bugs_dir = os.path.join(settings.MEDIA_ROOT, 'bugs')
print(f"  bugs dir exists: {os.path.exists(bugs_dir)}")
if os.path.exists(bugs_dir):
    files = os.listdir(bugs_dir)
    print(f"  files in bugs/: {len(files)}")
    for f in files[:5]:
        print(f"    {f}")
