# Sponsor Integration Design

**Date:** 2026-07-31
**Status:** Approved for planning
**Scope:** GMI Cloud, Agnes, OpenAI, and Zo Computer integrations

> **Implementation clarification (2026-07-31):** The available GMI credential
> is a Serverless Inference API key, not a GPU Compute allocation. The active
> GMI integration therefore performs an independent, OpenAI-compatible audit of
> aggregate measurements and draft coaching. The CUDA worker remains an
> optional production lane and must not be represented as live without a real
> GMI GPU runtime probe.

## Goal

Add truthful, testable sponsor integrations to Les Meilleurs without making any
provider a runtime prerequisite. The application will preserve its existing
deterministic analysis and coaching behavior when credentials, network access,
GPU capacity, or provider responses are unavailable.

The first complete product path is:

```text
analysis result
  -> deterministic evidence selection
  -> bounded frame extraction
  -> Agnes visual review when configured
  -> OpenAI specialist coaching when configured
  -> deterministic fallback for every unavailable or failed specialist
  -> evidence/provenance report in the mobile app
  -> optional Zo export and reminder
```

GMI Inference independently audits the coaching draft without replacing the
existing computer-vision pipeline. Optional GMI GPU Compute can own analysis
execution after deployment. Zo is an export/follow-up integration, not the
source of truth for analysis.

## Constraints

- Deterministic measurements remain authoritative for coordinates, timing,
  tracking quality, beat alignment, and scores.
- Provider success is recorded only after a real provider operation succeeds.
- Missing credentials produce `not_configured`; provider errors produce
  `failed`; useful non-provider output is marked `fallback`.
- No provider secret or raw video is sent to the Expo bundle or external APIs.
- Agnes receives at most three selected evidence moments, not the full video.
- The deterministic Observation quality gate remains authoritative before
  Timing or Formation agents run.
- OpenAI agent tools are read-only, typed, session-scoped, and cannot accept
  arbitrary SQL, storage paths, or model names.
- Zo exports are private or unlisted only; reminders are explicit user actions.
- The mobile app remains on Expo SDK 54 and receives no sponsor SDKs.
- Live provider smoke tests are opt-in and require explicit environment flags.

## Architecture

### Shared backend contracts

Add `IntegrationRun`, `EvidenceMoment`, `EvidenceFrame`, `VisualReview`, and
`ZoExportRequest`/`ZoExportResponse` contracts. Extend `CoachingReport` with
optional evidence, integration, and trace fields while preserving legacy fields
and parsing behavior. Store MVP evidence, provider runs, and export metadata in
the existing JSONB result metadata.

Each provider adapter exposes availability and returns a typed result plus an
`IntegrationRun`. Adapters never raise a provider-specific failure into the
main coaching path; the orchestration layer records the failure and selects the
existing deterministic counterpart.

### Evidence pipeline

`backend/app/services/evidence/selector.py` ranks observation, timing,
formation, comparison, and tracking signals. It normalizes finite metrics,
merges timestamps within roughly one second, prefers category diversity, limits
the result to the configured maximum, and rejects moments without source
frames. The selector is pure and deterministic.

`frames.py` extracts bounded JPEG images at selected timestamps, pairs reference
and attempt frames for comparison mode, hashes each image, and cleans temporary
files. It never makes original uploads public.

### Sponsor responsibilities

- **GMI:** use Serverless Inference for a bounded audit of aggregate metrics and
  draft coaching, with explicit model/request/latency/token provenance. Retain
  runtime CUDA diagnostics and the separate image as an optional GPU Compute
  lane. Local CPU execution remains supported.
- **Agnes:** add a configurable OpenAI-compatible image adapter with strict
  structured output validation, content restrictions, bounded concurrency, and
  cache keys based on image hashes, metric context, model, and schema version.
- **OpenAI:** add the Agents SDK behind the coaching boundary. Deterministic
  Python controls the Observation gate; typed tools expose narrow metric and
  evidence subsets; specialist and synthesis failures fall back independently.
- **Zo:** add a compact versioned export artifact, idempotent publish behavior,
  optional reminder creation, and local-report preservation on export failure.

### Mobile experience

Extend `CoachReport` normalization with optional evidence and integration
arrays. Add evidence cards, a provenance drawer, and a Zo export card. Evidence
cards must jump the relevant timeline; the timeline components therefore gain
an explicit seek callback/ref boundary rather than relying on hidden local
state. Legacy reports render without the new fields.

The results screen leads with user value: score or formation summary, next
action, visual analysis, evidence, coaching, export, then a collapsed
“How this analysis was produced” section. Sponsor names and statuses are
secondary provenance, not the primary experience.

## Error handling and privacy

- Provider timeouts, malformed JSON, invalid confidence, unsupported claims,
  and inaccessible media produce a recorded failure and deterministic fallback.
- Agnes prompts explicitly prohibit identity, sensitive-trait, health, injury,
  emotion, and timing claims unsupported by still images.
- Trace metadata contains IDs, categories, timing, and non-sensitive metrics;
  image bytes and private URLs are excluded.
- Zo artifacts omit credentials, internal IDs, expiring signed URLs, raw frame
  arrays, and full agent traces.
- UI distinguishes completed, running, fallback, not configured, and failed.

## Verification evidence path

The primary claim is that a completed report can show measured evidence,
truthful provider provenance, and safe fallback behavior.

Evidence will come from:

1. Pure selector tests proving stable, diverse, bounded timestamps.
2. Adapter tests proving structured validation, timeout handling, redaction,
   and accurate status transitions without network calls.
3. API tests proving report compatibility, session scoping, cached calls, and
   Zo idempotency.
4. Mobile tests proving legacy parsing, evidence rendering, timeline seeking,
   and export states.
5. Explicit live smoke tests for one short fixture per configured provider.
6. A final end-to-end fixture run whose report contains timestamps, image
   hashes, provider statuses, fallback reasons, and export metadata.

The system cannot establish live GMI, Agnes, OpenAI, or Zo availability without
credentials and reachable services. In that case, verification will establish
correct `not_configured`/`fallback` behavior instead and will state the live
coverage limitation.

## Delivery phases

1. Shared contracts, settings, health, persistence, and tests.
2. GMI diagnostics, CUDA image, deployment assets, and provenance.
3. Evidence selection, frame extraction, Agnes adapter, and coaching wiring.
4. OpenAI Agents SDK orchestration, tools, structured output, and tracing.
5. Zo artifact export, idempotency, reminder isolation, and API tests.
6. Expo models, timeline seek boundary, evidence/provenance UI, export UX, and
   mobile tests.

Each phase must leave the deterministic local path working and must be verified
before the next phase begins.
