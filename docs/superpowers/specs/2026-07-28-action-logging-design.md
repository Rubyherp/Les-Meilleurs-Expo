# Action Logging — Design Spec

**Date:** 2026-07-28
**Status:** draft

## Summary

Add human-readable console logging for every user action and loading event across both the Expo frontend and the Python FastAPI backend. Logs are always-on (not gated by `__DEV__`), use a consistent timestamped category format, and are purely additive — no existing behavior changes.

## Requirements

1. All user interactions logged to console: button presses, form inputs, screen navigation, API calls, phase transitions, state changes
2. Backend logs every HTTP request/response, Celery task phase, and error
3. Consistent `[HH:MM:SS.mmm][CATEGORY] message` format across frontend and backend
4. Logs never throw — failures are silently swallowed
5. No logging of sensitive data (raw URIs, user content)
6. Always active, not gated by dev/production

## Architecture

### Frontend: `src/utils/logger.ts`

A typed logger utility with category-specific methods. All console output flows through this module — no ad-hoc `console.log` calls elsewhere.

```typescript
logger.ui.press(label)       // Button/tap targets
logger.ui.navigate(from, to) // Screen transitions
logger.ui.input(field, action) // Form field changes
logger.api.request(method, path) // Outgoing HTTP
logger.api.response(method, path, status, durationMs) // HTTP response
logger.phase(message)        // Analysis phase transitions
logger.store.action(name, payload?) // Zustand state mutations
logger.error(context, err)   // Caught errors with context
logger.system(message)       // App lifecycle events
```

Output format: `[14:23:05.123][UI:PRESS] Start Session`

### Backend: `backend/app/core/logger.py`

A Python logger wrapping stdlib `logging` with a custom `Formatter` that prepends the category tag. All backend output uses this.

```python
logger.api(method, path, extra?)  # HTTP request/response
logger.task(task_name, message)   # Celery task progress
logger.phase(phase_name)          # Pipeline phase transitions
logger.error(context, detail)     # Errors with context
```

Output format: `[14:23:05.456][TASK] run_analysis: starting phase: pose estimation`

### Categories

| Category | Prefix | Used by |
|---|---|---|
| UI press | `[UI:PRESS]` | Frontend only |
| UI navigate | `[UI:NAV]` | Frontend only |
| UI input | `[UI:INPUT]` | Frontend only |
| API request | `[API:REQ]` | Frontend `request()` wrapper |
| API response | `[API:RES]` | Frontend `request()` wrapper |
| API (backend) | `[API]` | Backend middleware + route handlers |
| Phase | `[PHASE]` | Both — frontend analysis screen, backend tasks |
| Store | `[STORE]` | Frontend Zustand store |
| Task | `[TASK]` | Backend Celery tasks |
| Error | `[ERROR]` | Both |
| System | `[SYSTEM]` | Frontend app lifecycle |

## Integration Points

### Frontend — Files to modify

| File | Changes |
|---|---|
| `src/utils/logger.ts` | **New.** Logger module implementation |
| `src/services/remoteAnalysisApi.ts` | Wrap `request()` with `logger.api.request` / `logger.api.response`. Log duration with `Date.now()` |
| `src/store/useAppStore.ts` | Add `logger.store.action()` in each mutation (createSession, updateSession, analyze, seedFromBackend, seedComparisonFromBackend, setShowingCreate, setPresentedSession). Add `logger.error()` in catch blocks |
| `app/_layout.tsx` | Use expo-router `useSegments()` or `usePathname()` to log `logger.ui.navigate()` on route changes |
| `app/(tabs)/practice.tsx` | `logger.ui.press` on "Start a new session" CTA |
| `app/(tabs)/groups.tsx` | `logger.ui.press` on each placeholder button |
| `app/(tabs)/profile.tsx` | `logger.ui.press` on each settings row tap |
| `app/create-session.tsx` | `logger.ui.press` on Mode A / Mode B selection |
| `app/create-mode-a.tsx` | `logger.ui.press` on camera, library, video selection, toggle, analyze button; `logger.ui.input` on title changes; `logger.error` on failures |
| `app/create-mode-b.tsx` | `logger.ui.press` on camera, library, reference/attempt selection, toggle, continue button; `logger.ui.input` on title changes; `logger.error` on failures |
| `app/analysis/[id].tsx` | `logger.phase()` at each `safeSetPhase()` call; `logger.ui.press` on retry; `logger.error` on failures |
| `src/components/PrimaryButton.tsx` | Optional: Add `logger.ui.press` in onPress. Alternatively log at each call site. |

### Backend — Files to modify

| File | Changes |
|---|---|
| `backend/app/core/logger.py` | **New.** Python logger module |
| `backend/app/main.py` | Add FastAPI middleware: log every request on entry, log response with status + duration on exit |
| `backend/app/api/routes.py` | `logger.api()` at session creation, calibration submission, upload completion, comparison trigger. `logger.error()` in exception handlers |
| `backend/app/tasks/analysis.py` | `logger.phase()` at each pipeline stage (detection → tracking → pose → projection → done). `logger.error()` in catch blocks |

## Non-Requirements

- No analytics service integration (Sentry, PostHog, etc.)
- No log persistence to disk or database
- No log levels (info/warn/debug) — everything is plain console output
- No structured JSON output
- No redaction of PII (no PII is logged)
- No log rotation or file output

## Guardrails

- **No-throw:** Every logger function wraps internally so a logging failure never propagates
- **Minimal overhead:** `Date.now()` / `time.time()` for timestamps; no string interpolation before checking if logging is active
- **No sensitive data:** Session IDs and file paths only — no raw URIs, video content, or personal data
