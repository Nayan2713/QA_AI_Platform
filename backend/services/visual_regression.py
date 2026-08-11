"""
services/visual_regression.py

Compares a new screenshot against the stored baseline for a page+step.
Uses pure Python (Pillow) — no JS dependencies needed.

Install:  pip install Pillow
"""

import os
import base64
import logging
from io import BytesIO
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Threshold: if diff percentage exceeds this, mark as FAILED visual regression
DIFF_THRESHOLD_PERCENT = float(getattr(settings, 'VISUAL_DIFF_THRESHOLD', 2.0))

# Where to store baseline + diff images on disk
VISUAL_MEDIA_ROOT = Path(getattr(settings, 'MEDIA_ROOT', 'media')) / 'visual_regression'


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def _base64_to_image(b64_string: str):
    """Convert a base64 string (with or without data-URI prefix) to a PIL Image."""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow is required: pip install Pillow")

    if ',' in b64_string:
        b64_string = b64_string.split(',', 1)[1]
    raw = base64.b64decode(b64_string)
    return Image.open(BytesIO(raw)).convert('RGB')


def _image_to_path(image, path: Path) -> str:
    """Save a PIL Image to disk and return its relative path string."""
    _ensure_dir(path.parent)
    image.save(str(path), format='PNG')
    return str(path.relative_to(Path(settings.MEDIA_ROOT)))


def save_baseline(page_id: int, step_number: int, screenshot_b64: str, width=1280, height=800) -> 'VisualBaseline':
    """
    Save or replace the baseline screenshot for a page+step.
    Called on first run when no baseline exists yet.
    """
    from core.models import VisualBaseline, Page

    image = _base64_to_image(screenshot_b64)
    save_path = VISUAL_MEDIA_ROOT / f'baselines' / f'page_{page_id}_step_{step_number}.png'
    rel_path = _image_to_path(image, save_path)

    baseline, _ = VisualBaseline.objects.update_or_create(
        page_id=page_id,
        step_number=step_number,
        defaults={
            'screenshot_path': rel_path,
            'width': width,
            'height': height,
        }
    )
    logger.info(f"[VisualRegression] Saved baseline page={page_id} step={step_number}")
    return baseline


def compare_screenshot(
    test_run_id: int,
    page_id: int,
    step_number: int,
    screenshot_b64: str,
) -> dict:
    """
    Compare a new screenshot against the stored baseline.

    Returns a dict:
    {
        'status': 'PASSED' | 'FAILED' | 'NO_BASELINE',
        'diff_percentage': float,
        'diff_path': str | None,
        'visual_diff_id': int | None,
    }
    """
    from core.models import VisualBaseline, VisualDiff, TestRun

    result = {
        'status': 'NO_BASELINE',
        'diff_percentage': 0.0,
        'diff_path': None,
        'visual_diff_id': None,
    }

    try:
        baseline = VisualBaseline.objects.get(page_id=page_id, step_number=step_number)
    except VisualBaseline.DoesNotExist:
        # No baseline — save this as the new baseline and return NO_BASELINE
        save_baseline(page_id, step_number, screenshot_b64)
        diff = VisualDiff.objects.create(
            test_run_id=test_run_id,
            baseline=None,
            step_number=step_number,
            status='NO_BASELINE',
            diff_percentage=0.0,
        )
        result['visual_diff_id'] = diff.id
        return result

    try:
        from PIL import Image, ImageChops
        import numpy as np

        # Load images
        new_image = _base64_to_image(screenshot_b64)
        baseline_path = Path(settings.MEDIA_ROOT) / baseline.screenshot_path
        baseline_image = Image.open(str(baseline_path)).convert('RGB')

        # Resize new image to match baseline dimensions
        if new_image.size != baseline_image.size:
            new_image = new_image.resize(baseline_image.size, Image.LANCZOS)

        # Pixel diff
        diff_image = ImageChops.difference(baseline_image, new_image)

        # Calculate percentage of changed pixels
        diff_array = np.array(diff_image)
        total_pixels = diff_array.shape[0] * diff_array.shape[1]
        changed_pixels = int(np.count_nonzero(diff_array.sum(axis=2)))
        diff_pct = (changed_pixels / total_pixels) * 100

        # Save diff image
        diff_path = VISUAL_MEDIA_ROOT / 'diffs' / f'run_{test_run_id}_step_{step_number}.png'
        rel_diff_path = _image_to_path(diff_image, diff_path)

        status = 'PASSED' if diff_pct <= DIFF_THRESHOLD_PERCENT else 'FAILED'

        diff_obj = VisualDiff.objects.create(
            test_run_id=test_run_id,
            baseline=baseline,
            step_number=step_number,
            diff_percentage=round(diff_pct, 2),
            diff_screenshot_path=rel_diff_path,
            status=status,
        )

        result.update({
            'status': status,
            'diff_percentage': round(diff_pct, 2),
            'diff_path': rel_diff_path,
            'visual_diff_id': diff_obj.id,
        })

        if status == 'FAILED':
            logger.warning(
                f"[VisualRegression] FAILED — run={test_run_id} page={page_id} "
                f"step={step_number} diff={diff_pct:.2f}%"
            )
        else:
            logger.info(
                f"[VisualRegression] PASSED — run={test_run_id} step={step_number} diff={diff_pct:.2f}%"
            )

    except ImportError:
        logger.error("[VisualRegression] Pillow or numpy not installed. pip install Pillow numpy")
    except Exception as e:
        logger.exception(f"[VisualRegression] Comparison failed: {e}")

    return result