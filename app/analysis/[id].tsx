import { useEffect, useState, useCallback, useRef } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useAppStore } from "@/store/useAppStore";
import ProcessingView from "@/components/ProcessingView";
import AnalysisResultsView from "@/components/AnalysisResultsView";

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
  const startedSessionId = useRef<string | null>(null);
  const sessionId = Array.isArray(id) ? id[0] : id;

  const session = sessions.find((s) => s.id === sessionId);
  const result = sessionId ? resultsBySession[sessionId] : undefined;
  const error = sessionId ? errorBySession[sessionId] : undefined;
  const participants = sessionId
    ? participantsBySession[sessionId] ?? []
    : [];

  const runAnalysis = useCallback(async (isRetry = false) => {
    if (
      !session ||
      result ||
      (!isRetry && startedSessionId.current === session.id)
    )
      return;
    startedSessionId.current = session.id;

    if (sessionId === SEED_SESSION_ID) {
      setPhase("analyzing");
      await seedFromBackend(SEED_SESSION_ID, SEED_BACKEND_SESSION_ID);
      setPhase("completed");
      return;
    }

    if (sessionId === SEED_COMPARISON_SESSION_ID) {
      setPhase("analyzing");
      await seedComparisonFromBackend(
        SEED_COMPARISON_SESSION_ID,
        SEED_COMPARISON_BACKEND_ID
      );
      setPhase("completed");
      return;
    }

    setPhase("preparing");
    try {
      await new Promise((resolve) => setTimeout(resolve, 450));
      setPhase("uploading");
      await new Promise((resolve) => setTimeout(resolve, 350));
      setPhase("analyzing");
      await analyze(session);
      setPhase("completed");
    } catch {
      setPhase("failed");
    }
  }, [session, result, analyze, seedFromBackend, seedComparisonFromBackend, sessionId]);

  useEffect(() => {
    runAnalysis();
  }, [runAnalysis]);

  if (!session) {
    return (
      <View className="flex-1 bg-lesBackground items-center justify-center">
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
      </View>
    );
  }

  if (result) {
    return (
      <AnalysisResultsView
        session={session}
        result={result}
        participants={participants}
        onPracticeAgain={() => {
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
    );
  }

  return (
    <ProcessingView
      session={session}
      phase={phase === "failed" || error ? "failed" : phase}
      errorMessage={error}
      onRetry={() => runAnalysis(true)}
      onClose={() => router.back()}
    />
  );
}
