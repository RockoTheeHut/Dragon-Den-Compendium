import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.utils import timezone

from compendium.management.commands.import_fightclub_xml import import_fightclub_xml_path

from .models import CompendiumImportJob, UserImportedObject


_IMPORT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="compendium-import")


def run_import_job(job_id):
    close_old_connections()
    temp_path = None
    try:
        job = CompendiumImportJob.objects.select_related("user").get(pk=job_id)
        if job.status == CompendiumImportJob.Status.SUCCEEDED:
            return

        job.status = CompendiumImportJob.Status.RUNNING
        job.started_at = timezone.now()
        job.result_message = "Import in progress..."
        job.save(update_fields=["status", "started_at", "result_message", "updated_at"])

        import_path = Path(job.import_path)
        if not job.use_server_xml:
            temp_path = import_path

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
        CompendiumImportJob.objects.filter(pk=job_id).update(
            status=CompendiumImportJob.Status.FAILED,
            result_message=f"Import failed: {exc}",
            completed_at=timezone.now(),
        )
    except Exception as exc:  # noqa: BLE001
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
