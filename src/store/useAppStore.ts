import { create } from "zustand";
import {
  DanceSession,
  createDanceSession,
  DanceSessionMediaOptions,
} from "../models/DanceSession";
import {
  GroupParticipant,
  createGroupParticipants,
} from "../models/GroupParticipant";
import { AnalysisResult } from "../models/AnalysisResult";
import { normalizePhase4Result } from "../models/Phase4Result";
import { normalizePhase5Result } from "../models/Phase5Result";
import { Phase5ResultJson } from "../models/Phase5Result";
import { analyzeSession } from "../services/analysisPipeline";
import { getRemoteResults } from "../services/remoteAnalysisApi";

const SEED_SESSION_ID = "11111111-1111-1111-1111-111111111111";
const SEED_COMPARISON_SESSION_ID = "22222222-2222-2222-2222-222222222222";

interface AppState {
  sessions: DanceSession[];
  participantsBySession: Record<string, GroupParticipant[]>;
  isShowingCreate: boolean;
  presentedSession: DanceSession | null;
  analyzingSessionId: string | null;
  resultsBySession: Record<string, AnalysisResult>;
  errorBySession: Record<string, string>;

  setShowingCreate: (show: boolean) => void;
  setPresentedSession: (session: DanceSession | null) => void;
  createSession: (
    title: string,
    isGroup: boolean,
    mediaOptions?: DanceSessionMediaOptions
  ) => DanceSession;
  updateSession: (sessionID: string, patch: Partial<DanceSession>) => void;
  analyze: (session: DanceSession) => Promise<void>;
  seedFromBackend: (
    targetSessionId: string,
    backendSessionId: string
  ) => Promise<void>;
  seedComparisonFromBackend: (
    targetSessionId: string,
    backendSessionId: string
  ) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  sessions: [
    {
      id: SEED_SESSION_ID,
      title: "Preview your first trend",
      recordedAt: 1_700_000_000_000, // 2023-11-14 in ms
      duration: 18.6,
      participantIDs: [],
    },
    {
      id: SEED_COMPARISON_SESSION_ID,
      title: "Compare two takes",
      recordedAt: 1_700_000_000_000,
      duration: 18.6,
      participantIDs: [],
    },
  ],
  participantsBySession: {},
  isShowingCreate: false,
  presentedSession: null,
  analyzingSessionId: null,
  resultsBySession: {},
  errorBySession: {},

  setShowingCreate: (show) => set({ isShowingCreate: show }),
  setPresentedSession: (session) => set({ presentedSession: session }),

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
    set((state) => ({
      sessions: [session, ...state.sessions],
      participantsBySession: {
        ...state.participantsBySession,
        [session.id]: participants,
      },
    }));
    return session;
  },

  updateSession: (sessionID, patch) =>
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === sessionID ? { ...session, ...patch } : session
      ),
    })),

  seedFromBackend: async (targetSessionId, backendSessionId) => {
    set((state) => ({
      analyzingSessionId: targetSessionId,
      errorBySession: {
        ...state.errorBySession,
        [targetSessionId]: undefined as unknown as string,
      },
    }));
    try {
      const remoteResults = await getRemoteResults(backendSessionId);
      const phase4 = normalizePhase4Result(remoteResults.metadata);
      if (!phase4) {
        throw new Error("The server returned no usable Phase 4 movement result.");
      }
      const result: AnalysisResult = {
        id: `${targetSessionId}-seeded`,
        sessionID: targetSessionId,
        analyzedAt: Date.now(),
        overallScore: 0,
        issues: [],
        participantResults: [],
        phase4,
      };
      set((state) => ({
        resultsBySession: {
          ...state.resultsBySession,
          [targetSessionId]: result,
        },
        analyzingSessionId: null,
      }));
    } catch (err) {
      set((state) => ({
        errorBySession: {
          ...state.errorBySession,
          [targetSessionId]:
            err instanceof Error
              ? err.message
              : "Could not seed data from the backend.",
        },
        analyzingSessionId: null,
      }));
    }
  },

  seedComparisonFromBackend: async (targetSessionId, backendSessionId) => {
    set((state) => ({
      analyzingSessionId: targetSessionId,
      errorBySession: {
        ...state.errorBySession,
        [targetSessionId]: undefined as unknown as string,
      },
    }));
    try {
      const remoteResults = await getRemoteResults(backendSessionId);
      const comparison = normalizePhase5Result(
        remoteResults.metadata as unknown as Phase5ResultJson
      );
      if (!comparison) {
        throw new Error("The server returned no usable Phase 5 comparison result.");
      }
      const result: AnalysisResult = {
        id: `${targetSessionId}-seeded-compare`,
        sessionID: targetSessionId,
        analyzedAt: Date.now(),
        overallScore: comparison.overallScore,
        issues: [],
        participantResults: [],
        comparison,
      };
      set((state) => ({
        resultsBySession: {
          ...state.resultsBySession,
          [targetSessionId]: result,
        },
        analyzingSessionId: null,
      }));
    } catch (err) {
      set((state) => ({
        errorBySession: {
          ...state.errorBySession,
          [targetSessionId]:
            err instanceof Error
              ? err.message
              : "Could not seed comparison data from the backend.",
        },
        analyzingSessionId: null,
      }));
    }
  },

  analyze: async (session) => {
    set((state) => {
      const errorBySession = { ...state.errorBySession };
      delete errorBySession[session.id];
      return { analyzingSessionId: session.id, errorBySession };
    });
    try {
      const result = await analyzeSession(session, {
        onRemoteSession: (remoteSessionID) =>
          get().updateSession(session.id, { remoteSessionID }),
        onRemoteTask: (remoteTaskID) =>
          get().updateSession(session.id, { remoteTaskID }),
      });
      set((state) => ({
        resultsBySession: {
          ...state.resultsBySession,
          [session.id]: result,
        },
        analyzingSessionId: null,
      }));
    } catch (err) {
      set((state) => ({
        errorBySession: {
          ...state.errorBySession,
          [session.id]:
            err instanceof Error
              ? err.message
              : "We could not finish this analysis. Your session is still saved as a draft.",
        },
        analyzingSessionId: null,
      }));
    }
  },
}));
