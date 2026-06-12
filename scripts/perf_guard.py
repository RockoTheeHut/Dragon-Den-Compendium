#!/usr/bin/env python
import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dragon_den.settings.local")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.core.exceptions import ObjectDoesNotExist  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

from compendium.models import GameObject  # noqa: E402
from tracker.models import TurnTrackerEntry  # noqa: E402


RUN_PREFIX = f"__perf_guard_{os.getpid()}_{int(time.time() * 1000)}__"


@dataclass
class CheckResult:
    name: str
    ms: float
    queries: int
    bytes: int
    ok: bool
    failures: list[str]


def _measure(client, method, url, iterations, data=None, **extra):
    data = data or {}
    times = []
    query_counts = []
    response_bytes = 0

    # Warmup
    if method == "get":
        client.get(url, **extra)
    else:
        client.post(url, data, **extra)

    for _ in range(iterations):
        start = time.perf_counter()
        with CaptureQueriesContext(connection) as ctx:
            if method == "get":
                response = client.get(url, **extra)
            else:
                response = client.post(url, data, **extra)
        elapsed_ms = (time.perf_counter() - start) * 1000
        times.append(elapsed_ms)
        query_counts.append(len(ctx.captured_queries))
        response_bytes = len(response.content)

        if response.status_code != 200:
            raise RuntimeError(f"Request failed for {url}. status={response.status_code}")

    return statistics.median(times), max(query_counts), response_bytes


def _build_compendium_fixture():
    # Build candidates for linkification/reference detection.
    candidates = []
    for index in range(1, 101):
        candidates.append(
            GameObject(
                system="dnd5e",
                object_type=GameObject.ObjectType.SPELL,
                name=f"{RUN_PREFIX} Spell {index}",
                source=GameObject.SourceType.CUSTOM,
                description="",
                data={"text": f"Spell body {index}"},
            )
        )
        candidates.append(
            GameObject(
                system="dnd5e",
                object_type=GameObject.ObjectType.ITEM,
                name=f"{RUN_PREFIX} Item {index}",
                source=GameObject.SourceType.CUSTOM,
                description="",
                data={"text": f"Item body {index}"},
            )
        )
    GameObject.objects.bulk_create(candidates, batch_size=200)

    referenced_lines = []
    for index in range(1, 101):
        referenced_lines.append(
            f"Gain access to {RUN_PREFIX} Spell {index} and {RUN_PREFIX} Item {index}."
        )

    detail_obj = GameObject.objects.create(
        system="dnd5e",
        object_type=GameObject.ObjectType.CLASS,
        name=f"{RUN_PREFIX} Class Anchor",
        source=GameObject.SourceType.IMPORTED,
        data={
            "hd": "8",
            "autolevel": [
                {
                    "_attributes": {"level": "1"},
                    "feature": [
                        {
                            "name": "Reference Heavy Feature",
                            "text": " ".join(referenced_lines),
                        }
                    ],
                }
            ],
        },
    )
    return detail_obj


def _build_tracker_fixture(user):
    entries = [
        TurnTrackerEntry(
            user=user,
            name=f"{RUN_PREFIX} Entry {index}",
            entry_type=TurnTrackerEntry.EntryType.ENEMY,
            is_active=True,
            sort_order=index,
            initiative=index % 30,
            hp_current=10,
            hp_max=10,
        )
        for index in range(120)
    ]
    TurnTrackerEntry.objects.bulk_create(entries, batch_size=200)
    return TurnTrackerEntry.objects.filter(user=user, name__startswith=RUN_PREFIX).order_by("id").first()


def _evaluate(name, measured_ms, measured_queries, measured_bytes, limits):
    failures = []
    if measured_ms > limits["max_ms"]:
        failures.append(f"ms {measured_ms:.1f} > {limits['max_ms']}")
    if measured_queries > limits["max_queries"]:
        failures.append(f"queries {measured_queries} > {limits['max_queries']}")
    if measured_bytes > limits["max_bytes"]:
        failures.append(f"bytes {measured_bytes} > {limits['max_bytes']}")
    return CheckResult(
        name=name,
        ms=measured_ms,
        queries=measured_queries,
        bytes=measured_bytes,
        ok=not failures,
        failures=failures,
    )


def _emit(check):
    status = "PASS" if check.ok else "FAIL"
    line = (
        f"[{status}] {check.name}: "
        f"{check.ms:.1f}ms, {check.queries} queries, {check.bytes} bytes"
    )
    print(line)
    if not check.ok:
        print("  Reasons: " + "; ".join(check.failures))
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(
                f"::warning title=Perf regression::{check.name} "
                f"failed thresholds: {'; '.join(check.failures)}"
            )


def _parse_args():
    parser = argparse.ArgumentParser(description="Run lightweight performance regression checks.")
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Do not fail with non-zero status even if thresholds are exceeded.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=int(os.getenv("PERF_GUARD_ITERATIONS", "5")),
        help="Number of measured iterations per route (default: 5).",
    )
    parser.add_argument(
        "--skip-timing",
        action="store_true",
        help="Only enforce query-count and payload-size budgets; skip wall-clock "
        "thresholds (useful on noisy shared CI runners).",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    iterations = max(args.iterations, 1)
    user, _ = User.objects.get_or_create(username=f"{RUN_PREFIX}_user")
    user.set_password("pw12345!")
    user.save(update_fields=["password"])

    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(user)

    TurnTrackerEntry.objects.filter(user=user, name__startswith=RUN_PREFIX).delete()
    GameObject.objects.filter(name__startswith=RUN_PREFIX).delete()

    detail_object = _build_compendium_fixture()
    first_entry = _build_tracker_fixture(user)

    # Note: with SQLite transaction_mode=IMMEDIATE, the explicit BEGIN inside
    # transaction.atomic views is counted as a query, so write routes carry +1.
    thresholds = {
        "compendium_detail": {"max_ms": 160, "max_queries": 8, "max_bytes": 450000},
        # Byte budget includes the per-form hidden encounter_id inputs that pin
        # tracker actions to their encounter.
        "tracker_dashboard": {"max_ms": 180, "max_queries": 6, "max_bytes": 760000},
        "tracker_quick_update": {"max_ms": 35, "max_queries": 7, "max_bytes": 15000},
    }
    if args.skip_timing:
        for limits in thresholds.values():
            limits["max_ms"] = float("inf")

    checks = []
    try:
        try:
            detail_object = GameObject.objects.get(pk=detail_object.pk)
        except ObjectDoesNotExist as exc:
            raise RuntimeError("Perf guard fixture missing before measurements.") from exc

        ms, queries, size = _measure(
            client,
            "get",
            reverse("compendium:object_detail", args=[detail_object.pk]),
            iterations=iterations,
        )
        checks.append(
            _evaluate("compendium_detail", ms, queries, size, thresholds["compendium_detail"])
        )

        ms, queries, size = _measure(
            client,
            "get",
            reverse("tracker:dashboard"),
            iterations=iterations,
        )
        checks.append(
            _evaluate("tracker_dashboard", ms, queries, size, thresholds["tracker_dashboard"])
        )

        ms, queries, size = _measure(
            client,
            "post",
            reverse("tracker:quick_update_entry", args=[first_entry.pk]),
            iterations=iterations,
            data={"initiative": "17"},
            HTTP_HX_REQUEST="true",
        )
        checks.append(
            _evaluate("tracker_quick_update", ms, queries, size, thresholds["tracker_quick_update"])
        )
    finally:
        TurnTrackerEntry.objects.filter(user=user, name__startswith=RUN_PREFIX).delete()
        GameObject.objects.filter(name__startswith=RUN_PREFIX).delete()
        user.delete()

    has_failures = False
    print("Performance guard results:")
    for check in checks:
        _emit(check)
        has_failures = has_failures or (not check.ok)

    if has_failures and args.warn_only:
        print("Perf guard warning mode: thresholds exceeded, continuing startup.")
        return 0

    if has_failures:
        print("Perf guard failed. One or more thresholds were exceeded.")
        return 1

    print("Perf guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
