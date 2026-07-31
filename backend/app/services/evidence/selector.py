"""Deterministic evidence-moment selection from analysis result metadata.

Every decision is pure and repeatable: given the same input dict the same
ordered list of ``EvidenceMoment`` objects is always returned.  The selection
algorithm reads only pre-existing metadata, filters out invalid candidates,
merges temporally-adjacent events, enforces per-category diversity caps and
an overall maximum count, and sorts by metric severity.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, get_args

from app.integrations.models import EvidenceCategory, EvidenceMoment
from app.services.evidence.models import _Candidate

_MERGE_THRESHOLD_SECONDS = 1.0
_DEFAULT_CATEGORY: EvidenceCategory = "observation"

# Pre-compute valid categories for O(1) membership test
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(EvidenceCategory))


def _finite(value: Any) -> float | None:
    """Return *value* as a finite float, or ``None`` if it is NaN/Inf/not numeric."""
    try:
        f = float(value)
        if math.isfinite(f):
            return f
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _category(value: str) -> EvidenceCategory:
    """Coerce a candidate category string into a valid ``EvidenceCategory``."""
    if value in _VALID_CATEGORIES:
        return value  # type: ignore[return-value]
    return _DEFAULT_CATEGORY


def _extract_candidates(
    result: dict[str, Any],
    *,
    mode: str,
    is_group: bool,
) -> list[_Candidate]:
    """Walk the result metadata and produce ranked candidate moments."""
    candidates: list[_Candidate] = []

    # ── 1. Deviations (comparison mode only) ──────────────────────────
    if mode == "comparison":
        deviations: list[dict[str, Any]] = result.get("deviations") or []
        for dev in deviations:
            ts = _finite(dev.get("timestamp_seconds"))
            val = _finite(dev.get("mean_euclidean_deviation"))
            if ts is None or val is None:
                continue
            candidates.append(
                _Candidate(
                    category="comparison",
                    timestamp_seconds=ts,
                    metric_value=val,
                    reason=f"mean_euclidean_deviation={val:.4f}",
                    source_data={"source_deviation": val},
                    reference_timestamp_seconds=_finite(dev.get("reference_timestamp_seconds")),
                )
            )

        # Overall score deviation from perfect
        overall = _finite(result.get("overall_score"))
        if overall is not None:
            candidates.append(
                _Candidate(
                    category="general",
                    timestamp_seconds=0.0,
                    metric_value=max(0.0, 1.0 - overall),
                    reason=f"overall_score={overall:.3f}",
                    source_data={"overall_score": overall},
                )
            )

    # ── 2. Frame-level quality signals ────────────────────────────────
    frames: list[dict[str, Any]] = result.get("sampled_frames") or []
    for frame in frames:
        ts = _finite(frame.get("timestamp_seconds"))
        if ts is None:
            continue

        tracks: list[dict[str, Any]] = frame.get("tracks") or []

        # Detection / visibility — count missing detections as severity
        observed = [t for t in tracks if t.get("bbox_source") == "observed"]
        total = len(tracks)
        if total > 0:
            visibility_loss = 1.0 - len(observed) / total
            if visibility_loss > 0:
                candidates.append(
                    _Candidate(
                        category="observation",
                        timestamp_seconds=ts,
                        metric_value=visibility_loss,
                        reason=f"visibility_loss={visibility_loss:.3f}",
                    )
                )

        # Pose quality — average pose confidence
        confidences: list[float] = []
        for t in tracks:
            pose = t.get("pose")
            if isinstance(pose, dict):
                conf = _finite(pose.get("confidence", 0.5))
                if conf is not None:
                    confidences.append(conf)
        if confidences:
            mean_conf = sum(confidences) / len(confidences)
            loss = max(0.0, 1.0 - mean_conf)
            if loss > 0:
                candidates.append(
                    _Candidate(
                        category="observation",
                        timestamp_seconds=ts,
                        metric_value=loss,
                        reason=f"pose_quality_loss={loss:.3f}",
                    )
                )

        # Tracking drops — occluded / lost counts
        occluded = sum(1 for t in tracks if t.get("status") in ("occluded", "lost"))
        if occluded > 0:
            candidates.append(
                _Candidate(
                    category="tracking",
                    timestamp_seconds=ts,
                    metric_value=min(1.0, occluded / max(1, total)),
                    reason=f"track_drops={occluded}",
                )
            )

    # ── 3. Formation / spacing for groups ─────────────────────────────
    if is_group:
        formation_info = result.get("formation") or result.get("spacing") or {}
        spacing_var = _finite(formation_info.get("spacing_variation", 0))
        if spacing_var is not None and spacing_var > 0:
            candidates.append(
                _Candidate(
                    category="formation",
                    timestamp_seconds=0.0,
                    metric_value=min(1.0, spacing_var),
                    reason=f"spacing_variation={spacing_var:.3f}",
                )
            )

    return candidates


def _merge_adjacent(
    candidates: list[_Candidate],
    threshold_seconds: float = _MERGE_THRESHOLD_SECONDS,
) -> list[_Candidate]:
    """Merge candidates whose timestamps are within *threshold_seconds*.

    When merging, we keep the candidate with the highest ``metric_value``
    and drop the rest within the cluster.  Clusters are anchored at the
    first (earliest) candidate so they cannot grow transitively: every
    candidate in a cluster is within *threshold_seconds* of the anchor.
    """
    if not candidates:
        return []

    sorted_c = sorted(candidates, key=lambda c: c.timestamp_seconds)
    merged: list[_Candidate] = []
    current_cluster = [sorted_c[0]]

    for c in sorted_c[1:]:
        if c.timestamp_seconds - current_cluster[0].timestamp_seconds <= threshold_seconds:
            current_cluster.append(c)
        else:
            # Keep the highest-metric candidate in the cluster
            best = max(current_cluster, key=lambda x: x.metric_value)
            merged.append(best)
            current_cluster = [c]

    if current_cluster:
        best = max(current_cluster, key=lambda x: x.metric_value)
        merged.append(best)

    return merged


def _apply_category_diversity(
    candidates: list[_Candidate],
    max_moments: int,
) -> list[_Candidate]:
    """Ensure category diversity: at least one per available category, capped by max."""
    if not candidates or max_moments <= 0:
        return []

    selected: list[_Candidate] = []
    used_categories: set[str] = set()

    # First pass: pick the best from each category (at most one per category in first round)
    by_category: dict[str, list[_Candidate]] = {}
    for c in sorted(candidates, key=lambda x: x.metric_value, reverse=True):
        by_category.setdefault(c.category, []).append(c)

    # Round-robin: take best from each category, then second-best, etc.
    # until we hit max_moments
    category_lists = {cat: sorted(lst, key=lambda x: x.metric_value, reverse=True)
                      for cat, lst in by_category.items()}
    indices: dict[str, int] = {cat: 0 for cat in category_lists}

    while len(selected) < max_moments:
        added = False
        for cat in sorted(category_lists):  # deterministic order
            lst = category_lists[cat]
            idx = indices[cat]
            if idx < len(lst):
                selected.append(lst[idx])
                indices[cat] = idx + 1
                added = True
                if len(selected) >= max_moments:
                    break
        if not added:
            break

    return selected[:max_moments]


def _candidate_to_moment(candidate: _Candidate) -> EvidenceMoment:
    """Convert an internal candidate to an ``EvidenceMoment`` Pydantic model.

    When *candidate* carries a ``reference_timestamp_seconds`` the resulting
    moment's metadata includes the keys ``"needs_reference"`` and
    ``"reference_timestamps"`` so that ``prepare_evidence_images`` can pair
    the attempt frame with the corresponding reference frame.
    """
    metrics: dict[str, Any] = {
        "metric_value": round(candidate.metric_value, 6),
        **candidate.source_data,
    }
    if candidate.reference_timestamp_seconds is not None:
        metrics["reference_timestamp_seconds"] = candidate.reference_timestamp_seconds
        metrics["needs_reference"] = True

    primary = round(candidate.timestamp_seconds, 4)
    stable = f"{_category(candidate.category)}|{primary:.4f}|{candidate.reason}"
    moment_id = "ev_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
    severity = "high" if candidate.metric_value >= 0.67 else "medium" if candidate.metric_value >= 0.34 else "low"

    return EvidenceMoment(
        id=moment_id,
        start_seconds=max(0.0, round(primary - 0.5, 4)),
        end_seconds=round(primary + 0.5, 4),
        primary_timestamp_seconds=primary,
        category=_category(candidate.category),
        severity=severity,
        deterministic_reason=candidate.reason,
        deterministic_metrics=metrics,
    )


# ── Public API ────────────────────────────────────────────────────────

def select_evidence(
    result: dict[str, Any],
    *,
    mode: str,
    is_group: bool,
    max_moments: int,
    duration_seconds: float | None,
) -> list[EvidenceMoment]:
    """Select at most ``max_moments`` deterministic evidence moments.

    Parameters
    ----------
    result:
        Raw analysis result dictionary with ``sampled_frames``, ``deviations``,
        and other metadata populated by upstream pipeline stages.
    mode:
        ``"single"`` or ``"comparison"`` — controls which metadata paths are
        inspected for candidates.
    is_group:
        When ``True``, adds formation/spacing candidates if available.
    max_moments:
        Hard ceiling on returned moments.  ``0`` returns an empty list.
    duration_seconds:
        If provided, candidates whose ``timestamp_seconds`` exceed this
        value are silently discarded.  ``None`` disables the filter.

    Returns
    -------
    list[EvidenceMoment]
        Deterministic, deduplicated, and diversity-aware list ordered by
        decreasing metric severity.
    """
    if not isinstance(result, dict):
        return []
    if max_moments <= 0:
        return []

    # 1. Extract raw candidates from metadata
    candidates = _extract_candidates(result, mode=mode, is_group=is_group)

    # 2. Filter out-of-duration
    if duration_seconds is not None:
        candidates = [c for c in candidates if c.timestamp_seconds <= duration_seconds]

    # 3. Filter candidates without usable source-frame timestamps
    candidates = [c for c in candidates if math.isfinite(c.timestamp_seconds)]

    # 4. Merge adjacent timestamps
    candidates = _merge_adjacent(candidates)

    # 5. Sort by metric value (descending), breaking ties by timestamp (ascending)
    candidates.sort(key=lambda c: (-c.metric_value, c.timestamp_seconds))

    # 6. Apply category diversity and max cap
    candidates = _apply_category_diversity(candidates, max_moments)

    # 7. Convert to EvidenceMoment
    return [_candidate_to_moment(c) for c in candidates]
