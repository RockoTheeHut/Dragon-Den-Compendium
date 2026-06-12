import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.utils import timezone

from compendium.management.commands.import_fightclub_xml import import_fightclub_xml_path

from .models import CompendiumImportJob, UserImportedObject


logger = logging.getLogger(__name__)

_IMPORT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="compendium-import")

# Jobs run in an in-process thread pool, so a restart mid-import would leave
# them PENDING/RUNNING forever without this recovery window.
STALE_JOB_TIMEOUT = timedelta(hours=2)


def reap_stale_jobs():
    """Mark jobs orphaned by a crash/restart as failed so the UI unblocks."""
    cutoff = timezone.now() - STALE_JOB_TIMEOUT
    return CompendiumImportJob.objects.filter(
        status__in=[CompendiumImportJob.Status.PENDING, CompendiumImportJob.Status.RUNNING],
        updated_at__lt=cutoff,
    ).update(
        status=CompendiumImportJob.Status.FAILED,
        result_message="Import was interrupted by a server restart or timed out.",
        completed_at=timezone.now(),
    )


def run_import_job(job_id):
    close_old_connections()
    temp_path = None
    try:
        job = CompendiumImportJob.objects.select_related("user").get(pk=job_id)
        import_path = Path(job.import_path)
        if not job.use_server_xml:
            temp_path = import_path

        # Atomically claim the job so a duplicate submission can't run it twice.
        claimed = CompendiumImportJob.objects.filter(
            pk=job_id,
            status=CompendiumImportJob.Status.PENDING,
        ).update(
            status=CompendiumImportJob.Status.RUNNING,
            started_at=timezone.now(),
            result_message="Import in progress...",
            updated_at=timezone.now(),
        )
        if not claimed:
            temp_path = None  # whoever claimed the job owns its temp file
            return

        result = import_fightclub_xml_path(file_path=import_path, system=job.system)
        touched_ids = list(result.get("touched_object_ids") or [])
        if touched_ids:
            UserImportedObject.objects.bulk_create(
                [UserImportedObject(user=job.user, game_object_id=object_id) for object_id in touched_ids],
                ignore_conflicts=True,
            )

        job.status = CompendiumImportJob.Status.SUCCEEDED
        job.created_count = result["created"]
        job.updated_count = result["updated"]
        job.unchanged_count = result["unchanged"]
        job.result_message = (
            f"Import complete. Created={result['created']}, Updated={result['updated']}, Unchanged={result['unchanged']}"
        )
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "created_count",
                "updated_count",
                "unchanged_count",
                "result_message",
                "completed_at",
                "updated_at",
            ]
        )
    except CommandError as exc:
        logger.warning("Compendium import job %s failed: %s", job_id, exc)
        CompendiumImportJob.objects.filter(pk=job_id).update(
            status=CompendiumImportJob.Status.FAILED,
            result_message=f"Import failed: {exc}",
            completed_at=timezone.now(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Compendium import job %s crashed", job_id)
        CompendiumImportJob.objects.filter(pk=job_id).update(
            status=CompendiumImportJob.Status.FAILED,
            result_message=f"Import failed: {exc}",
            completed_at=timezone.now(),
        )
    finally:
        if temp_path and temp_path.exists():
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        close_old_connections()


def schedule_import_job(job_id):
    if getattr(settings, "COMPENDIUM_IMPORT_ASYNC", True):
        _IMPORT_EXECUTOR.submit(run_import_job, job_id)
        return
    run_import_job(job_id)
