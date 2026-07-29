import { useEffect, useState, useCallback, useRef } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { logger } from "@/utils/logger";
import { useAppStore } from "@/store/useAppStore";
import ProcessingView from "@/components/ProcessingView";
import AnalysisResultsView from "@/components/AnalysisResultsView";
import { triggerCoach, getCoachReport } from "@/services/coachApi";
import type { CoachResponse } from "@/models/CoachReport";

const SEED_SESSION_ID = "11111111-1111-1111-1111-111111111111";
const SEED_BACKEND_SESSION_ID = "ddd418e0-8893-4862-984a-5304b766805d";
const SEED_COMPARISON_SESSION_ID = "22222222-2222-2222-2222-222222222222";
// This will be replaced with the actual backend session ID after the comparison completes:
const SEED_COMPARISON_BACKEND_ID = "bae46a8b-eda1-4fa1-8245-256acb7e6640";

export default function AnalysisScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const sessions = useAppStore((state) => state.sessions);
  const resultsBySession = useAppStore((state) => state.resultsBySession);
  const errorBySession = useAppStore((state) => state.errorBySession);
  const participantsBySession = useAppStore(
    (state) => state.participantsBySession
  );
  const analyze = useAppStore((state) => state.analyze);
  const seedFromBackend = useAppStore((state) => state.seedFromBackend);
  const seedComparisonFromBackend = useAppStore((state) => state.seedComparisonFromBackend);
  const setShowingCreate = useAppStore((state) => state.setShowingCreate);
  const router = useRouter();
  const [phase, setPhase] = useState("preparing");
  const [coachResponse, setCoachResponse] = useState<CoachResponse | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachError, setCoachError] = useState<string | null>(null);
  const startedSessionId = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const sessionId = Array.isArray(id) ? id[0] : id;

  // Safe setPhase that respects unmount
  const safeSetPhase = useCallback((p: string) => {
    if (mountedRef.current) setPhase(p);
  }, []);

  const session = sessions.find((s) => s.id === sessionId);
  const result = sessionId ? resultsBySession[sessionId] : undefined;
  const error = sessionId ? errorBySession[sessionId] : undefined;
  const participants = sessionId
    ? participantsBySession[sessionId] ?? []
    : [];

  const requestCoach = useCallback(async () => {
    if (!sessionId || !session?.remoteSessionID) return;
    setCoachLoading(true);
    setCoachError(null);
    try {
      const backendId = session.remoteSessionID;
      const result = await triggerCoach(backendId);
      if (result.status === "completed") {
        setCoachResponse(result);
      } else {
        await new Promise((r) => setTimeout(r, 1500));
        const polled = await getCoachReport(backendId);
        setCoachResponse(polled);
      }
    } catch (e) {
      setCoachError(e instanceof Error ? e.message : "Coaching unavailable");
    } finally {
      setCoachLoading(false);
    }
  }, [sessionId, session?.remoteSessionID]);

  const runAnalysis = useCallback(async (isRetry = false) => {
    if (
      !session ||
      result ||
      (!isRetry && startedSessionId.current === session.id)
    )
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

  useEffect(() => {
    mountedRef.current = true;
    runAnalysis();
    return () => {
      mountedRef.current = false;
    };
  }, [runAnalysis]);

  if (!session) {
    return (
      <SafeAreaView edges={["top", "bottom"]} className="flex-1 bg-lesBackground">
        <ProcessingView
          session={{
            title: "",
            id: "",
          }}
          phase="failed"
          errorMessage="Session not found"
          onRetry={() => router.back()}
          onClose={() => router.back()}
        />
      </SafeAreaView>
    );
  }

  if (result) {
    return (
      <SafeAreaView edges={["top", "bottom"]} className="flex-1 bg-lesBackground">
        <AnalysisResultsView
          session={session}
          result={result}
          participants={participants}
          coachResponse={coachResponse}
          coachLoading={coachLoading}
          coachError={coachError}
          onRequestCoach={requestCoach}
          onPracticeAgain={() => {
            logger.ui.press("Practice again");
            router.back();
            setTimeout(() => setShowingCreate(true), 100);
            setTimeout(
              () =>
                router.push(
                  sessionId === SEED_COMPARISON_SESSION_ID
                    ? "/create-mode-b"
                    : "/create-session"
                ),
              200
            );
          }}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={["top", "bottom"]} className="flex-1 bg-lesBackground">
      <ProcessingView
        session={session}
        phase={phase === "failed" || error ? "failed" : phase}
        errorMessage={error}
        onRetry={() => {
          logger.ui.press("Retry analysis");
          runAnalysis(true);
        }}
        onClose={() => {
          logger.ui.press("Close analysis");
          router.back();
        }}
      />
    </SafeAreaView>
  );
}
