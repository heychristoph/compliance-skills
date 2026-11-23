# Copied from shared/lib/sampling.py by tools/sync.py. Edit that file, not this copy.
"""Seeded, reproducible sample selection shared by every audit engine.

The sample sizes live in `sampling.yaml` next to this file (a firm replaces them with
its own methodology). The engines decide what the population is; this module decides
how many items to test and which ones, from a seed recorded in the workpaper.
"""

from __future__ import annotations

import datetime as dt
import random

from .io import LIB, AuditError, load_yaml, parse_date

FREQUENCIES = ["annual", "semiannual", "quarterly", "monthly", "weekly", "daily", "multiple-daily", "event", "continuous"]
NATURES = ["manual", "automated", "itdm"]  # itdm: IT-dependent manual


def rules() -> dict:
    return load_yaml(LIB / "sampling.yaml")


def plan(*, seed: str, freq: str, nature: str, start: dt.date, end: dt.date, point_in_time: bool,
         population: tuple[str, list[str]] | None = None, sample_size: str = "") -> dict:
    """The plan block for one control or unit. Deterministic for a given seed.

    `population` is (artifact ID, item IDs already filtered to the period). Without one,
    the population is the calendar occurrences of a periodic control, a single instance
    of an automated or continuous control, or, at a point in time, the latest performance.
    `sample_size` is the auditor's documented override from testplan.csv ("" for none).
    """
    table = rules()
    rng = random.Random(seed)
    if population:
        source, items = population
        pop = {"source": source, "size": len(items)}
    elif freq in ("continuous",) or nature == "automated":
        items, pop = ["instance-1"], None
    elif point_in_time:
        items, pop = ["latest"], None  # the most recent performance on or before the as-of date
    else:
        items = occurrences(freq, start, end)
        pop = {"source": "periods", "size": len(items)}

    if point_in_time:
        size = min(table["point_in_time"], len(items))
    elif sample_size:
        size = min(int(sample_size), len(items))
    elif nature == "automated" or freq == "continuous":
        size = min(table["automated"], len(items))
    elif freq == "event" or population:
        size = event_size(table["event"], len(items))
    else:
        size = min(table["periodic"][freq], len(items))

    chosen = sorted(rng.sample(items, size)) if size < len(items) else list(items)
    return {"frequency": freq, "nature": nature, "population": pop, "sample_size": len(chosen), "sample": chosen, "seed": seed}


def event_window(engagement):
    """Which event dates (hires, terminations, changes) a connector keeps: every event up to the as-of date for a
    point-in-time engagement (SOC 2 Type 1, ISO Stage 1, assessments), the period's events otherwise."""
    start, end = engagement.period
    as_of = getattr(engagement, "point_in_time", None)
    as_of = bool(as_of) if as_of is not None else getattr(engagement, "report_type", None) == 1
    return (lambda d: d <= end) if as_of else (lambda d: start <= d <= end)


def in_period(value: str | None, start: dt.date, end: dt.date, point_in_time: bool) -> bool:
    """Whether a population item's date counts: on or before the as-of date, or inside the period."""
    d = parse_date(value)
    if point_in_time:
        return d is None or d <= end
    return d is not None and start <= d <= end


def occurrences(freq: str, start: dt.date, end: dt.date) -> list[str]:
    """Calendar occurrences of a periodic activity that fall in [start, end], as stable labels."""
    if freq == "annual":
        return sorted({str(y) for y in range(start.year, end.year + 1)})
    if freq in ("semiannual", "quarterly", "monthly"):
        step = {"semiannual": 6, "quarterly": 3, "monthly": 1}[freq]
        labels, y, m = [], start.year, ((start.month - 1) // step) * step + 1
        while dt.date(y, m, 1) <= end:
            if freq == "monthly":
                labels.append(f"{y}-{m:02d}")
            elif freq == "quarterly":
                labels.append(f"{y}-Q{(m - 1) // 3 + 1}")
            else:
                labels.append(f"{y}-H{(m - 1) // 6 + 1}")
            m += step
            if m > 12:
                y, m = y + 1, m - 12
        return labels
    if freq == "weekly":
        labels, d = [], start
        while d <= end:
            iso = d.isocalendar()
            label = f"{iso[0]}-W{iso[1]:02d}"
            if label not in labels:
                labels.append(label)
            d += dt.timedelta(days=1)
        return labels
    if freq in ("daily", "multiple-daily"):
        return [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    raise AuditError(f"Frequency '{freq}' has no calendar occurrences; give the control a population file.")


def event_size(table: list[dict], n: int) -> int:
    for rule in table:
        if rule["max_population"] is None or n <= rule["max_population"]:
            return n if rule["size"] == "all" else min(rule["size"], n)
    return n
