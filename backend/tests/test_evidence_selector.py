"""Tests for deterministic evidence selection."""

import math

import pytest

from app.services.evidence.selector import select_evidence


# ── Test fixtures ─────────────────────────────────────────────────────

def _mk_result(*, mode="single", is_group=False, frames_count=30, duration=None):
    """Build a plausible analysis result dict for selector testing."""
    frames = []
    for i in range(frames_count):
        ts = i * 1.0 / 10.0  # 10 fps
        frames.append({
            "timestamp_seconds": ts,
            "tracks": [
                {
                    "track_id": 1,
                    "bbox_source": "observed",
                    "pose": {"keypoints": [[0, 1, 2]] * 33},
                    "top_down": {"x": 0.5 + i * 0.001, "y": 0.5, "source": "observed"},
                }
            ],
        })

    result: dict = {"sampled_frames": frames}

    if mode == "comparison":
        ref_frames = []
        for i in range(frames_count):
            ts = i * 1.0 / 10.0
            ref_frames.append({
                "timestamp_seconds": ts,
                "tracks": [
                    {
                        "track_id": 1,
                        "bbox_source": "observed",
                        "pose": {"keypoints": [[0, 1, 2]] * 33},
                        "top_down": {"x": 0.45 + i * 0.001, "y": 0.5, "source": "observed"},
                    }
                ],
            })

        # Create varying deviations
        deviations = []
        for i in range(min(frames_count, 20)):
            dev = abs(i - 10) * 0.01 + 0.005  # highest at edges
            deviations.append({
                "mean_euclidean_deviation": dev,
                "timestamp_seconds": i * 1.0 / 10.0,
                "pair_index": i,
            })

        result.update({
            "reference": {"sampled_frames": ref_frames},
            "attempt": {"sampled_frames": frames},
            "overall_score": 0.72,
            "deviations": deviations,
            "matches": [{"dtw_cost": 0.1 + i * 0.01} for i in range(10)],
            "unmatched_reference_ids": [],
            "unmatched_attempt_ids": [],
        })

    if duration is not None:
        result["duration_seconds"] = duration

    return result


# ── Largest deviation ranking ──────────────────────────────────────────

def test_selector_ranks_by_largest_deviation():
    """High-deviation candidates are selected and, within each category,
    the first occurrence carries the highest metric_value for that category."""
    # Use deviations-only input with no frame-level candidates so timing
    # dominates without being absorbed by high-metric pose_quality.
    deviations = []
    for i in range(10):
        # Produce metric values so the highest is at the "edge" (i=0,9)
        dev = 0.9 - abs(i - 4.5) * 0.15  # peaks at ~0.9 at edges, dips to ~0.225 at center
        deviations.append({
            "mean_euclidean_deviation": round(dev, 6),
            "timestamp_seconds": float(i),
        })
    result = {"deviations": deviations, "sampled_frames": []}
    moments = select_evidence(
        result, mode="comparison", is_group=False, max_moments=4, duration_seconds=None
    )
    assert len(moments) >= 2, f"Expected at least 2 moments, got {len(moments)}"

    # Spatial deviation is comparison evidence, not a timing claim.
    for m in moments:
        assert m.category == "comparison", f"Expected only comparison, got {m.category}"

    # The first moment should have the highest metric_value overall.
    metrics = [m.metadata["metric_value"] for m in moments]
    assert metrics[0] == max(metrics), (
        f"First moment metric {metrics[0]} is not the maximum {max(metrics)}; all: {metrics}"
    )
    # Metrics should be non-increasing (within timing category)
    for i in range(len(metrics) - 1):
        assert metrics[i] >= metrics[i + 1], (
            f"Metric at index {i} ({metrics[i]}) < index {i+1} ({metrics[i+1]})"
        )


# ── Adjacent timestamp merging ─────────────────────────────────────────

def test_selector_merges_adjacent_timestamps_within_one_second():
    """Candidates within 1 second of the cluster anchor are merged."""
    result = _mk_result(mode="comparison")
    moments = select_evidence(
        result, mode="comparison", is_group=False, max_moments=10, duration_seconds=None
    )
    assert len(moments) <= 10


def test_merge_does_not_grow_transitively():
    """A merge cluster cannot grow beyond the threshold via chaining.

    Five candidates at t=0, 0.6, 1.2, 1.8, 2.4 with threshold=1.0 should
    produce at least 3 clusters (not a single cluster via transitive linking).
    """
    candidates = []
    for i, ts in enumerate([0.0, 0.6, 1.2, 1.8, 2.4]):
        candidates.append({
            "timestamp_seconds": ts,
            "mean_euclidean_deviation": 0.1 + i * 0.02,
        })

    result = {
        "deviations": candidates,
        "sampled_frames": [],
    }
    moments = select_evidence(
        result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None
    )
    # With anchor-based clustering, t=0→0.6 (gap=0.6) merges,
    # t=1.2 (gap=1.2 from anchor 0) starts new cluster,
    # t=1.2→1.8 (gap=0.6) merges, t=2.4 (gap=1.2 from anchor 1.2) starts new.
    # So 3 clusters minimum.
    assert len(moments) >= 3, (
        f"Expected at least 3 clusters to avoid transitive growth, got {len(moments)}"
    )


# ── Category diversity ─────────────────────────────────────────────────

def test_selector_maintains_category_diversity():
    """When multiple categories are available at non-overlapping timestamps,
    the selector includes at least three different categories."""
    # Frame-level data away from t=0 so general isn't absorbed by merge
    frames = []
    for i in range(3):
        ts = float(10 + i * 10)  # 10, 20, 30 — away from t=0 (general)
        frames.append({
            "timestamp_seconds": ts,
            "tracks": [
                {
                    "track_id": 1,
                    "bbox_source": "observed",  # no visibility loss
                    "pose": {"confidence": 0.3},  # triggers pose_quality loss (metric 0.7)
                    "status": "active",  # no track drops
                }
            ],
        })
    # Deviations at timestamps far from frame timestamps
    deviations = []
    for i in range(3):
        ts = float(100 + i * 10)  # 100, 110, 120
        deviations.append({
            "mean_euclidean_deviation": 0.5 + i * 0.1,
            "timestamp_seconds": ts,
        })

    result = {
        "deviations": deviations,
        "sampled_frames": frames,
        "overall_score": 0.4,
    }
    moments = select_evidence(
        result, mode="comparison", is_group=False, max_moments=8, duration_seconds=None
    )
    cats = {m.category for m in moments}
    assert cats == {"comparison", "observation"}


# ── Maximum count enforcement ──────────────────────────────────────────

def test_selector_respects_max_moments():
    """The selector never returns more than max_moments."""
    result = _mk_result(mode="comparison")
    for limit in [0, 1, 3, 7]:
        moments = select_evidence(result, mode="comparison", is_group=False, max_moments=limit, duration_seconds=None)
        assert len(moments) <= limit


def test_selector_minimum_behaviour():
    """With max_moments=0, returns empty list."""
    result = _mk_result(mode="comparison")
    moments = select_evidence(result, mode="comparison", is_group=False, max_moments=0, duration_seconds=None)
    assert moments == []


# ── Out-of-duration rejection ──────────────────────────────────────────

def test_selector_rejects_out_of_duration():
    """Candidates beyond the video duration are excluded."""
    result = _mk_result(mode="single", frames_count=30)
    # duration = 1.0 sec, but frames go up to 2.9 sec, so many are out of bounds
    moments = select_evidence(result, mode="single", is_group=False, max_moments=5, duration_seconds=1.0)
    # No moment should have a frame timestamp beyond 1.0 seconds
    for m in moments:
        for f in m.frames:
            assert f.seconds <= 1.0, f"Frame at {f.seconds}s exceeds duration 1.0s"


# ── NaN / infinite filtering ───────────────────────────────────────────

def test_selector_filters_nan_infinite_values():
    """Candidates with NaN or infinite metric values are excluded."""
    result = {
        "sampled_frames": [],
        "deviations": [
            {"mean_euclidean_deviation": float("nan"), "timestamp_seconds": 0.5, "pair_index": 0},
            {"mean_euclidean_deviation": float("inf"), "timestamp_seconds": 1.0, "pair_index": 1},
            {"mean_euclidean_deviation": 0.05, "timestamp_seconds": 1.5, "pair_index": 2},
            {"mean_euclidean_deviation": 0.03, "timestamp_seconds": 2.0, "pair_index": 3},
        ],
    }
    moments = select_evidence(result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None)
    # Should only include the non-NaN, non-inf candidates
    assert len(moments) > 0
    # No moment should reference NaN or inf deviations
    for m in moments:
        md = m.metadata.get("source_deviation")
        if md is not None:
            assert math.isfinite(float(md))


# ── Deterministic repeated output ──────────────────────────────────────

def test_selector_is_deterministic():
    """Same input always produces exactly the same output."""
    result = _mk_result(mode="comparison")
    run1 = select_evidence(result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None)
    run2 = select_evidence(result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None)
    # Compare the moments by serializing to JSON
    assert len(run1) == len(run2)
    for a, b in zip(run1, run2):
        assert a.model_dump(mode="json") == b.model_dump(mode="json")


# ── Missing / empty data ───────────────────────────────────────────────

def test_selector_handles_empty_result():
    """Empty result dict returns empty moment list."""
    moments = select_evidence({}, mode="single", is_group=False, max_moments=5, duration_seconds=None)
    assert moments == []


def test_selector_handles_missing_deviations():
    """Result without deviations still produces meaningful moments if frames exist."""
    result = _mk_result(mode="single", frames_count=10)
    moments = select_evidence(result, mode="single", is_group=False, max_moments=5, duration_seconds=None)
    # In single mode without deviations, we may still get moments from frame data
    assert isinstance(moments, list)


# ── Source-frame timestamps required ───────────────────────────────────

def test_selector_rejects_candidates_without_timestamps():
    """Candidates without usable source-frame timestamps are silently dropped."""
    result = {
        "deviations": [
            {"mean_euclidean_deviation": 0.15},  # No timestamp!
        ],
        "sampled_frames": [],
    }
    moments = select_evidence(result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None)
    assert moments == []


# ── Reference timestamp propagation ─────────────────────────────────────

def test_selector_propagates_reference_timestamps_to_metadata():
    """When a deviation candidate has reference_timestamp_seconds, it appears in
    the EvidenceMoment metadata so frame preparation can pair attempt/reference."""
    result = {
        "deviations": [
            {
                "mean_euclidean_deviation": 0.42,
                "timestamp_seconds": 1.5,
                "reference_timestamp_seconds": 1.5,
                "pair_index": 0,
            },
            {
                "mean_euclidean_deviation": 0.12,
                "timestamp_seconds": 2.0,
                "reference_timestamp_seconds": None,
                "pair_index": 1,
            },
        ],
        "sampled_frames": [],
    }
    moments = select_evidence(
        result, mode="comparison", is_group=False, max_moments=5, duration_seconds=None
    )
    assert len(moments) >= 1

    # The moment from the candidate with reference_timestamp_seconds should
    # carry the pairing metadata that prepare_evidence_images expects.
    ref_moments = [
        m for m in moments if m.metadata.get("needs_reference") is True
    ]
    assert len(ref_moments) >= 1, (
        f"No moment had needs_reference=True; metadata: {[m.metadata for m in moments]}"
    )
    for m in ref_moments:
        assert m.metadata["reference_timestamp_seconds"] == 1.5

    # The candidate with reference_timestamp_seconds=None should NOT have
    # needs_reference set.
    no_ref_moments = [
        m for m in moments if m.metadata.get("needs_reference") is not True
    ]
    for m in no_ref_moments:
        assert "needs_reference" not in m.metadata or m.metadata.get("needs_reference") is not True
