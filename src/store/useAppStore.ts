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
import { analyzeSession } from "../services/analysisPipeline";

const SEED_SESSION_ID = "11111111-1111-1111-1111-111111111111";

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
}

export const useAppStore = create<AppState>((set, get) => ({
  sessions: [
    {
      id: SEED_SESSION_ID,
      title: "Preview your first trend",
      recordedAt: 1_700_000_000_000, // 2023-11-14 in ms
      duration: 24,
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
