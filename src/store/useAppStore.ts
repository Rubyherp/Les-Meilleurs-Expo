import { create } from "zustand";
import {
  DanceSession,
  createDanceSession,
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
  createSession: (title: string, isGroup: boolean) => DanceSession;
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

  createSession: (title, isGroup) => {
    const participants = isGroup ? createGroupParticipants() : [];
    const session = createDanceSession(
      title,
      isGroup,
      24,
      participants.map((participant) => participant.id)
    );
    set((state) => ({
      sessions: [session, ...state.sessions],
      participantsBySession: {
        ...state.participantsBySession,
        [session.id]: participants,
      },
    }));
    return session;
  },

  analyze: async (session) => {
    set({ analyzingSessionId: session.id });
    try {
      const result = await analyzeSession(session);
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
            "We could not finish this analysis. Your session is still saved as a draft.",
        },
        analyzingSessionId: null,
      }));
    }
  },
}));
