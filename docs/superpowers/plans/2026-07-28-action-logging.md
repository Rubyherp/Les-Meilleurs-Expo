# Action Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add human-readable console logging for every user action and loading event across the Expo frontend and Python FastAPI backend.

**Architecture:** Two logger utility modules (TypeScript + Python) providing category-specific methods (`logger.ui.press()`, `logger.api.request()`, `logger.phase()`, etc.) that produce `[HH:MM:SS.mmm][CATEGORY] message` output. All existing interaction points are wired to call through these utilities — purely additive, no behavior changes.

**Tech Stack:** TypeScript (React Native/Expo), Python (FastAPI stdlib logging)

## Global Constraints

- Log format: `[HH:MM:SS.mmm][CATEGORY] message` on both frontend and backend
- Logs are always-on (not gated by `__DEV__`)
- Logging must never throw — failures are silently swallowed
- No sensitive data logged (session IDs ok, raw URIs not)
- Human-readable text format, not JSON

---

### Task 1: Create frontend logger module

**Files:**
- Create: `src/utils/logger.ts`

**Interfaces:**
- Produces: `logger` object with `.ui.press()`, `.ui.navigate()`, `.ui.input()`, `.api.request()`, `.api.response()`, `.phase()`, `.store.action()`, `.error()`, `.system()`

- [ ] **Step 1: Write the logger module**

```typescript
// src/utils/logger.ts

type LogCategory =
  | "UI:PRESS"
  | "UI:NAV"
  | "UI:INPUT"
  | "API:REQ"
  | "API:RES"
  | "PHASE"
  | "STORE"
  | "ERROR"
  | "SYSTEM";

function safeLog(category: LogCategory, message: string, data?: unknown) {
  try {
    const now = new Date();
    const timestamp =
      now.toISOString().slice(11, 23); // "HH:MM:SS.mmm"
    const prefix = `[${timestamp}][${category}]`;
    if (data !== undefined) {
      console.log(prefix, message, data);
    } else {
      console.log(prefix, message);
    }
  } catch {
    // Never let logging crash the app
  }
}

export const logger = {
  ui: {
    press: (label: string) => safeLog("UI:PRESS", label),
    navigate: (from: string, to: string) =>
      safeLog("UI:NAV", `${from} → ${to}`),
    input: (field: string, action: string) =>
      safeLog("UI:INPUT", `${field}: ${action}`),
  },
  api: {
    request: (method: string, path: string) =>
      safeLog("API:REQ", `${method} ${path}`),
    response: (
      method: string,
      path: string,
      status: number,
      durationMs: number,
    ) =>
      safeLog(
        "API:RES",
        `${method} ${path} → ${status} (${durationMs}ms)`,
      ),
  },
  phase: (message: string) => safeLog("PHASE", message),
  store: {
    action: (name: string, payload?: unknown) =>
      safeLog("STORE", name, payload),
  },
  error: (context: string, err: unknown) =>
    safeLog("ERROR", `${context}: ${err instanceof Error ? err.message : String(err)}`),
  system: (message: string) => safeLog("SYSTEM", message),
};
```

- [ ] **Step 2: Commit**

```bash
git add src/utils/logger.ts
git commit -m "feat: add frontend logger utility"
```

---

### Task 2: Add API call logging to remoteAnalysisApi

**Files:**
- Modify: `src/services/remoteAnalysisApi.ts`

**Interfaces:**
- Consumes: `logger` from `src/utils/logger`
- Produces: logged API requests and responses

- [ ] **Step 1: Import logger and wrap request()**

In `src/services/remoteAnalysisApi.ts`, add the import after the existing imports (after line 3):

```typescript
import { logger } from "../utils/logger";
```

Then modify the `request()` function (starting at line 92) to log entry and exit:

```typescript
async function request<T>(path: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  logger.api.request(method, path);
  const startedAt = Date.now();

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(joinUrl(requireBaseUrl(), path), {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
    logger.api.response(method, path, response.status, Date.now() - startedAt);
    const body = await response.json().catch(() => undefined);
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail?: unknown }).detail)
          : `Request failed with HTTP ${response.status}.`;
      throw new RemoteAnalysisError(detail, response.status);
    }
    return body as T;
  } catch (error) {
    if (error instanceof RemoteAnalysisError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new RemoteAnalysisError("The analysis server took too long to respond.");
    }
    throw new RemoteAnalysisError(
      error instanceof Error ? error.message : "The analysis server could not be reached."
    );
  } finally {
    clearTimeout(timeout);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/services/remoteAnalysisApi.ts
git commit -m "feat: add API request/response logging to remoteAnalysisApi"
```

---

### Task 3: Add store action logging

**Files:**
- Modify: `src/store/useAppStore.ts`

**Interfaces:**
- Consumes: `logger` from `src/utils/logger`

- [ ] **Step 1: Import logger and add logging in each store action**

In `src/store/useAppStore.ts`, add after line 1:

```typescript
import { logger } from "../utils/logger";
```

Then modify each action:

**`setShowingCreate` (line 73)** — add log before set:

```typescript
  setShowingCreate: (show) => {
    logger.store.action("setShowingCreate", { show });
    set({ isShowingCreate: show });
  },
```

**`setPresentedSession` (line 74)** — add log:

```typescript
  setPresentedSession: (session) => {
    logger.store.action("setPresentedSession", { sessionId: session?.id });
    set({ presentedSession: session });
  },
```

**`createSession` (line 76)** — add log after variable declarations, before set:

```typescript
  createSession: (title, isGroup, mediaOptions) => {
    const participants = isGroup ? createGroupParticipants() : [];
    const session = {
      ...createDanceSession(
      title,
      isGroup,
      24,
      participants.map((participant) => participant.id)
      ),
      ...mediaOptions,
    };
    logger.store.action("createSession", { id: session.id, title, isGroup });
    set((state) => ({
      sessions: [session, ...state.sessions],
      participantsBySession: {
        ...state.participantsBySession,
        [session.id]: participants,
      },
    }));
    return session;
  },
```

**`seedFromBackend` (line 104)** — add log at start and in catch:

```typescript
  seedFromBackend: async (targetSessionId, backendSessionId) => {
    logger.store.action("seedFromBackend", { targetSessionId, backendSessionId });
    set((state) => {
      const errorBySession = { ...state.errorBySession };
      delete errorBySession[targetSessionId];
      return { analyzingSessionId: targetSessionId, errorBySession };
    });
    try {
      // ... (rest unchanged)
    } catch (err) {
      logger.error("seedFromBackend", err);
      // ... (rest unchanged)
    }
  },
```

**`seedComparisonFromBackend` (line 148)** — same pattern:

```typescript
  seedComparisonFromBackend: async (targetSessionId, backendSessionId) => {
    logger.store.action("seedComparisonFromBackend", { targetSessionId, backendSessionId });
    // ... existing code ...
    } catch (err) {
      logger.error("seedComparisonFromBackend", err);
      // ... existing code ...
    }
  },
```

**`analyze` (line 194)** — add log at start and in catch:

```typescript
  analyze: async (session) => {
    logger.store.action("analyze", { sessionId: session.id });
    // ... existing code ...
    } catch (err) {
      logger.error("analyze", err);
      // ... existing code ...
    }
  },
```

- [ ] **Step 2: Commit**

```bash
git add src/store/useAppStore.ts
git commit -m "feat: add store action and error logging"
```

---

### Task 4: Add navigation logging

**Files:**
- Modify: `app/_layout.tsx`

**Interfaces:**
- Consumes: `logger` from `src/utils/logger`, expo-router `useSegments`

- [ ] **Step 1: Add navigation listener component**

Replace `app/_layout.tsx` with:

```typescript
import "../global.css";
import { useRef } from "react";
import { Stack, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { logger } from "@/utils/logger";

function NavigationLogger() {
  const segments = useSegments();
  const previous = useRef<string>("app");

  const current = segments.join("/") || "app";
  if (current !== previous.current) {
    logger.ui.navigate(previous.current, current);
    previous.current = current;
  }
  return null;
}

export default function RootLayout() {
  logger.system("App mounted");
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <NavigationLogger />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="create-session"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="create-mode-a"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="create-mode-b"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="analysis/[id]"
          options={{ presentation: "modal" }}
        />
      </Stack>
    </SafeAreaProvider>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/_layout.tsx
git commit -m "feat: add screen navigation logging to root layout"
```

---

### Task 5: Add logging to practice screen

**Files:**
- Modify: `app/(tabs)/practice.tsx`

- [ ] **Step 1: Import logger and add press logging**

Add import after line 3:

```typescript
import { logger } from "@/utils/logger";
```

Add logging in handlers:

```typescript
  const handleCreate = () => {
    logger.ui.press("Start a new session");
    store.setShowingCreate(true);
    router.push("/create-session");
  };

  const handleSessionPress = (session: any) => {
    logger.ui.press(`Open session: ${session.title}`);
    store.setPresentedSession(session);
    router.push(`/analysis/${session.id}`);
  };
```

- [ ] **Step 2: Commit**

```bash
git add "app/(tabs)/practice.tsx"
git commit -m "feat: add press logging to practice screen"
```

---

### Task 6: Add logging to groups screen

**Files:**
- Modify: `app/(tabs)/groups.tsx`

- [ ] **Step 1: Import logger and add press logging**

Add import after line 3:

```typescript
import { logger } from "@/utils/logger";
```

Add `logger.ui.press(...)` to each handler before the `Alert.alert`:

```typescript
  const handleCreateGroup = () => {
    logger.ui.press("Create group");
    Alert.alert(/* ... unchanged ... */);
  };

  const handleJoinWithCode = () => {
    logger.ui.press("Join with code");
    Alert.alert(/* ... unchanged ... */);
  };

  const handleViewGroup = () => {
    logger.ui.press("View group: Weekend Trend Crew");
    Alert.alert(/* ... unchanged ... */);
  };

  const handleNoGroups = () => {
    logger.ui.press("No groups yet");
    Alert.alert(/* ... unchanged ... */);
  };
```

- [ ] **Step 2: Commit**

```bash
git add "app/(tabs)/groups.tsx"
git commit -m "feat: add press logging to groups screen"
```

---

### Task 7: Add logging to profile screen

**Files:**
- Modify: `app/(tabs)/profile.tsx`

The profile screen has no interactive handlers currently (SettingsRow is display-only). No changes needed beyond potential future wiring.

- [ ] **Step 1: Commit**

```bash
git commit --allow-empty -m "chore: profile screen — no interactive actions to log"
```

---

### Task 8: Add logging to create-session screen

**Files:**
- Modify: `app/create-session.tsx`

- [ ] **Step 1: Import logger and add press logging**

Add import after line 4:

```typescript
import { logger } from "@/utils/logger";
```

In the `CreateSessionScreen` component, wrap the mode press handlers and close button:

```typescript
  // Modify the ModeCard onPress for Mode A (line 92):
  onPress={() => {
    logger.ui.press("Mode A: Build the formation");
    router.push("/create-mode-a");
  }}

  // Modify the ModeCard onPress for Mode B (line 100):
  onPress={() => {
    logger.ui.press("Mode B: Compare two takes");
    router.push("/create-mode-b");
  }}

  // Modify the Close button onPress (line 71):
  onPress={() => {
    logger.ui.press("Close new session");
    router.back();
  }}
```

- [ ] **Step 2: Commit**

```bash
git add app/create-session.tsx
git commit -m "feat: add press logging to create-session screen"
```

---

### Task 9: Add logging to create-mode-a screen

**Files:**
- Modify: `app/create-mode-a.tsx`

- [ ] **Step 1: Import logger**

Add import after line 6:

```typescript
import { logger } from "@/utils/logger";
```

- [ ] **Step 2: Add logging calls**

**Back button** (line 116):
```typescript
  onPress={() => {
    logger.ui.press("Back (Mode A)");
    router.back();
  }}
```

**Title input** (line 140) — add onChangeText logging:
```typescript
  onChangeText={(text) => {
    setTitle(text);
    logger.ui.input("title", "changed");
  }}
```

**Group switch** (line 149):
```typescript
  onValueChange={(value) => {
    setIsGroup(value);
    logger.ui.input("group choreography", value ? "on" : "off");
  }}
```

**Record now** (line 170):
```typescript
  onPress={() => {
    logger.ui.press("Record now (Mode A)");
    showCamera();
  }}
```

**Choose video** (line 176):
```typescript
  onPress={() => {
    logger.ui.press("Choose video (Mode A)");
    pickVideo();
  }}
```

**Camera Record button** (line 208):
```typescript
  onPress={() => {
    logger.ui.press(isRecording ? "Stop recording (Mode A)" : "Start recording (Mode A)");
    if (isRecording) cancelCamera();
    else recordVideo();
  }}
```

**Camera Cancel button** (line 214):
```typescript
  onPress={() => {
    logger.ui.press("Cancel camera (Mode A)");
    cancelCamera();
  }}
```

**Analyze button** (line 242) — wrap handleAnalyze to log:
```typescript
  const handleAnalyze = () => {
    logger.ui.press("Build my formation (analyze)");
    const session = store.createSession(title, isGroup, {
      attemptVideoUri: videoUri,
      calibrationCorners,
    });
    router.dismissAll();
    setTimeout(() => {
      store.setPresentedSession(session);
      router.push(`/analysis/${session.id}`);
    }, 100);
  };
```

- [ ] **Step 3: Commit**

```bash
git add app/create-mode-a.tsx
git commit -m "feat: add press and input logging to create-mode-a screen"
```

---

### Task 10: Add logging to create-mode-b screen

**Files:**
- Modify: `app/create-mode-b.tsx`

- [ ] **Step 1: Import logger**

Add import after line 9:

```typescript
import { logger } from "@/utils/logger";
```

- [ ] **Step 2: Add logging calls**

**Back button** (line 151):
```typescript
  onPress={() => {
    logger.ui.press("Back (Mode B)");
    router.back();
  }}
```

**Title input** (line 177):
```typescript
  onChangeText={(text) => {
    setTitle(text);
    logger.ui.input("title", "changed");
  }}
```

**Group switch** (line 183):
```typescript
  onValueChange={(value) => {
    setIsGroup(value);
    logger.ui.input("group choreography", value ? "on" : "off");
  }}
```

**Choose reference** (line 188):
```typescript
  onPress={() => {
    logger.ui.press("Choose reference video (Mode B)");
    pickVideo(true);
  }}
```

**Add my attempt / Continue button** (line 202):
```typescript
  onPress={() => {
    logger.ui.press("Add my attempt");
    setStep("attempt");
  }}
```

**Record now** (line 223):
```typescript
  onPress={() => {
    logger.ui.press("Record now (Mode B)");
    showCamera();
  }}
```

**Choose video** (line 229):
```typescript
  onPress={() => {
    logger.ui.press("Choose video (Mode B)");
    pickVideo(false);
  }}
```

**Camera Record button** (line 258):
```typescript
  onPress={() => {
    logger.ui.press(isRecording ? "Stop recording (Mode B)" : "Start recording (Mode B)");
    if (isRecording) cancelCamera();
    else recordAttempt();
  }}
```

**Camera Cancel button** (line 264):
```typescript
  onPress={() => {
    logger.ui.press("Cancel camera (Mode B)");
    cancelCamera();
  }}
```

**Analyze button** (line 292) — wrap handleAnalyze to log:
```typescript
  const handleAnalyze = () => {
    logger.ui.press("Analyze my practice (Mode B)");
    const session = store.createSession(title, isGroup, {
      attemptVideoUri,
      referenceVideoUri,
      calibrationCorners,
    });
    router.dismissAll();
    setTimeout(() => {
      store.setPresentedSession(session);
      router.push(`/analysis/${session.id}`);
    }, 100);
  };
```

- [ ] **Step 3: Commit**

```bash
git add app/create-mode-b.tsx
git commit -m "feat: add press and input logging to create-mode-b screen"
```

---

### Task 11: Add phase and interaction logging to analysis screen

**Files:**
- Modify: `app/analysis/[id].tsx`

- [ ] **Step 1: Import logger**

Add import after line 3:

```typescript
import { logger } from "@/utils/logger";
```

- [ ] **Step 2: Add phase logging in safeSetPhase and other interactions**

Modify `safeSetPhase` at line 33 to also log:

```typescript
  const safeSetPhase = useCallback((p: string) => {
    if (mountedRef.current) {
      const prevPhase = phase; // Note: this captures phase at render time via closure
      setPhase((current) => {
        // Use functional update to always log the actual previous phase
        logger.phase(`${current} → ${p}`);
        return p;
      });
    }
  }, []);
```

Hmm, that approach reveals we need to refactor slightly. Instead, add explicit log calls at each phase transition in `runAnalysis`. This is clearer:

In `runAnalysis` (lines 44-93), add `logger.phase()` at each `safeSetPhase` call:

```typescript
  const runAnalysis = useCallback(async (isRetry = false) => {
    if (!session || result || (!isRetry && startedSessionId.current === session.id))
      return;
    startedSessionId.current = session.id;

    if (sessionId === SEED_SESSION_ID) {
      logger.phase("preparing → analyzing (seed)");
      safeSetPhase("analyzing");
      try {
        await seedFromBackend(SEED_SESSION_ID, SEED_BACKEND_SESSION_ID);
        logger.phase("analyzing → completed (seed)");
        safeSetPhase("completed");
      } catch {
        logger.phase("analyzing → failed (seed)");
        safeSetPhase("failed");
      }
      return;
    }

    if (sessionId === SEED_COMPARISON_SESSION_ID) {
      logger.phase("preparing → analyzing (seed comparison)");
      safeSetPhase("analyzing");
      try {
        await seedComparisonFromBackend(
          SEED_COMPARISON_SESSION_ID,
          SEED_COMPARISON_BACKEND_ID
        );
        logger.phase("analyzing → completed (seed comparison)");
        safeSetPhase("completed");
      } catch {
        logger.phase("analyzing → failed (seed comparison)");
        safeSetPhase("failed");
      }
      return;
    }

    if (!mountedRef.current) return;
    logger.phase("initial → preparing");
    safeSetPhase("preparing");
    try {
      await new Promise((resolve) => setTimeout(resolve, 450));
      if (!mountedRef.current) return;
      logger.phase("preparing → uploading");
      safeSetPhase("uploading");
      await new Promise((resolve) => setTimeout(resolve, 350));
      if (!mountedRef.current) return;
      logger.phase("uploading → analyzing");
      safeSetPhase("analyzing");
      await analyze(session);
      if (!mountedRef.current) return;
      logger.phase("analyzing → completed");
      safeSetPhase("completed");
    } catch {
      logger.phase("→ failed");
      safeSetPhase("failed");
    }
  }, [session, result, analyze, seedFromBackend, seedComparisonFromBackend, sessionId, safeSetPhase]);
```

Also add press logging for "Practice again" button (line 127):

```typescript
          onPracticeAgain={() => {
            logger.ui.press("Practice again");
            // ... rest unchanged ...
          }}
```

And for retry (line 151):

```typescript
          onRetry={() => {
            logger.ui.press("Retry analysis");
            runAnalysis(true);
          }}
```

And for close (line 152):

```typescript
          onClose={() => {
            logger.ui.press("Close analysis");
            router.back();
          }}
```

- [ ] **Step 3: Commit**

```bash
git add "app/analysis/[id].tsx"
git commit -m "feat: add phase and interaction logging to analysis screen"
```

---

### Task 12: Create backend logger module

**Files:**
- Create: `backend/app/core/logger.py`

**Interfaces:**
- Produces: `logger` object with `.api()`, `.task()`, `.phase()`, `.error()`

- [ ] **Step 1: Write the Python logger module**

```python
# backend/app/core/logger.py

import logging
import time
from datetime import datetime, timezone


class AppFormatter(logging.Formatter):
    """Custom formatter that prepends [HH:MM:SS.mmm][CATEGORY] to each log record."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        category = getattr(record, "category", "SYSTEM")
        return f"[{timestamp}][{category}] {record.getMessage()}"


_logger = logging.getLogger("lesmeilleurs")
_logger.setLevel(logging.INFO)
_logger.handlers.clear()

handler = logging.StreamHandler()
handler.setFormatter(AppFormatter())
_logger.addHandler(handler)


class Logger:
    """Structured logger for the Les Meilleurs backend."""

    @staticmethod
    def api(method: str, path: str, extra: str = "") -> None:
        """Log an API event (request received, response sent)."""
        msg = f"{method} {path}"
        if extra:
            msg += f" - {extra}"
        _logger.info(msg, extra={"category": "API"})

    @staticmethod
    def task(task_name: str, message: str) -> None:
        """Log a Celery task event."""
        _logger.info(f"{task_name}: {message}", extra={"category": "TASK"})

    @staticmethod
    def phase(phase_name: str) -> None:
        """Log a pipeline phase transition."""
        _logger.info(phase_name, extra={"category": "PHASE"})

    @staticmethod
    def error(context: str, detail: str = "") -> None:
        """Log an error with context."""
        msg = f"{context}"
        if detail:
            msg += f": {detail}"
        _logger.error(msg, extra={"category": "ERROR"})


logger = Logger()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/logger.py
git commit -m "feat: add backend logger utility"
```

---

### Task 13: Add logging middleware to FastAPI

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add request/response logging middleware**

Replace `backend/app/main.py` with:

```python
import time

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router, prefix=settings.api_prefix)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.api(request.method, request.url.path, "request received")
    started_at = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - started_at) * 1000)
    logger.api(
        request.method,
        request.url.path,
        f"response {response.status_code} ({duration_ms}ms)",
    )
    return response


@app.get("/health", include_in_schema=False)
async def root_health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add HTTP request/response logging middleware"
```

---

### Task 14: Add route-level logging

**Files:**
- Modify: `backend/app/api/routes.py`

- [ ] **Step 1: Import logger and add route logs**

Add import after line 4:

```python
from app.core.logger import logger
```

Add logging calls at key decision points:

**`create_session` (line 69):**

```python
@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session(db: AsyncSession = Depends(get_db)) -> SessionCreateResponse:
    session = AnalysisSession()
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.api("POST", f"/sessions/{session.id}", "session created")
    return SessionCreateResponse(
        session_id=session.id,
        status=session.status,
        created_at=session.created_at,
    )
```

**`set_calibration` (line 82):**

```python
@router.post("/sessions/{session_id}/calibration", response_model=CalibrationResponse)
async def set_calibration(
    session_id: UUID,
    payload: CalibrationRequest,
    db: AsyncSession = Depends(get_db),
) -> CalibrationResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    session.calibration = {"points": [list(point) for point in payload.points]}
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/calibration", "calibration saved")
    return CalibrationResponse(session_id=session_id, points=payload.points)
```

**`store_reference_video` (line 126):**

```python
    media = await _store_video(session_id, video, db, storage, role="reference")
    db.add(media)
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/reference", f"media_id={media.id}")
    return RoleMediaResponse(session_id=session_id, media_id=media.id, role="reference")
```

**`store_attempt_video` (line 145):**

```python
    media = await _store_video(session_id, video, db, storage, role="attempt")
    db.add(media)
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/attempt", f"media_id={media.id}")
    return RoleMediaResponse(session_id=session_id, media_id=media.id, role="attempt")
```

**`create_comparison` (line 164) — log after job creation:**

```python
    session.status = "queued"
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.api("POST", f"/sessions/{session_id}/compare", f"job_id={job.id} mode={job.mode}")
```

**`create_comparison` — log enqueue error (line 222):**

In the catch block after raising HTTPException, add:
```python
    except Exception as exc:
        logger.error("compare enqueue", str(exc))
        # ... rest unchanged ...
```

**`upload_video` (line 234) — log after job creation:**

```python
    db.add_all([media, job])
    await db.commit()
    await db.refresh(job)
    logger.api("POST", f"/sessions/{session_id}/upload", f"media_id={media.id} job_id={job.id}")
```

**`upload_video` — log enqueue error (line 262):**

In the catch block:
```python
    except Exception as exc:
        logger.error("upload enqueue", str(exc))
        # ... rest unchanged ...
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes.py
git commit -m "feat: add route-level logging for session operations"
```

---

### Task 15: Add task phase logging

**Files:**
- Modify: `backend/app/tasks/analysis.py`

- [ ] **Step 1: Import logger**

Add import after line 5:

```python
from app.core.logger import logger
```

- [ ] **Step 2: Add phase logging in `_process_job`**

In `_process_job` (line 124), add phase logs at each transition point.

After job status is set to "processing" (line 147):
```python
        job.status = "processing"
        job.progress = 5
        if session:
            session.status = "processing"
        await db.commit()
        logger.task("run_analysis", f"job {job_id} started — mode={job.mode}")
```

Before the comparison branch starts (line 163):
```python
        if job.mode == "comparison":
            logger.phase("starting reference pipeline")
            # ... rest unchanged ...
```

After reference completes and before attempt starts — add after line 191, before attempt_result assignment:
```python
            logger.phase("reference complete → starting attempt pipeline")
            attempt_result = await _run_pipeline_for_media(
```

After attempt completes — add after attempt_result assignment (line 194) but before compare_result_metadata:
```python
            logger.phase("attempt complete → running comparison")
            result_metadata = compare_result_metadata(
```

After comparison completes — add after `await _set_progress(job_id, "processing", 95)`:
```python
            await _set_progress(job_id, "processing", 95)
            logger.phase("comparison complete → writing results")
```

Before results are written (line 218):
```python
        logger.phase(f"writing results for job {job_id}")
        existing_result = (
```

After job completes (line 227):
```python
        if session:
            session.status = "completed"
        await db.commit()
        logger.task("run_analysis", f"job {job_id} completed successfully")
```

- [ ] **Step 3: Add error logging in `_run_job`**

In `_run_job` (line 233), add error logging before re-raising:

```python
async def _run_job(job_id: UUID) -> None:
    try:
        await _process_job(job_id)
    except Exception as exc:
        logger.error(f"run_analysis job {job_id}", str(exc))
        await _set_failed(job_id, str(exc))
        raise
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks/analysis.py
git commit -m "feat: add task phase logging to analysis pipeline"
```
