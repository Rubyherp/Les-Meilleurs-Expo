import { View, Text, Pressable, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import CoachAgentCard from "./CoachAgentCard";
import type { CoachResponse } from "@/models/CoachReport";

interface Props {
  coachResponse: CoachResponse | null | undefined;
  loading: boolean;
  error: string | null;
  onTrigger: () => void;
}

function SkeletonCard() {
  return (
    <View className="rounded-2xl border border-lesLine bg-white/40 p-4 gap-3 animate-pulse">
      <View className="flex-row gap-2">
        <View className="h-5 w-16 rounded-full bg-lesLine" />
        <View className="h-5 w-32 rounded bg-lesLine" />
      </View>
      <View className="h-4 w-full rounded bg-lesLine" />
      <View className="h-4 w-2/3 rounded bg-lesLine" />
      <View className="h-1 w-full rounded-full bg-lesLine" />
    </View>
  );
}

export default function CoachFeedbackView({ coachResponse, loading, error, onTrigger }: Props) {
  // Loading
  if (loading) {
    return (
      <View className="gap-[22px]">
        <View className="flex-row items-center gap-2 px-1">
          <ActivityIndicator size="small" color="#FF5C5C" />
          <Text className="text-sm text-lesMuted">Generating coaching insights...</Text>
        </View>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </View>
    );
  }

  // Error
  if (error) {
    return (
      <View className="rounded-2xl border border-[#FF5C5C]/30 bg-[#FF5C5C]/5 p-4 gap-3">
        <View className="flex-row items-center gap-2">
          <Ionicons name="warning-outline" size={18} color="#FF5C5C" />
          <Text className="text-sm font-semibold text-[#FF5C5C]">Coaching unavailable</Text>
        </View>
        <Text className="text-xs text-lesMuted">{error}</Text>
        <Pressable onPress={onTrigger} className="self-start rounded-lg bg-lesCoral px-4 py-2">
          <Text className="text-xs font-semibold text-white">Try again</Text>
        </Pressable>
      </View>
    );
  }

  // Not triggered yet
  if (!coachResponse) {
    return (
      <Pressable onPress={onTrigger} className="rounded-2xl border border-lesCoral/30 bg-[#FF5C5C]/5 p-4 items-center gap-2">
        <Ionicons name="sparkles-outline" size={24} color="#FF5C5C" />
        <Text className="text-sm font-semibold text-lesCoral">Run coaching agents</Text>
        <Text className="text-xs text-lesMuted text-center">
          Observation and timing for solo; formation joins for groups.
        </Text>
      </Pressable>
    );
  }

  // Not configured
  if (coachResponse.status === "not_configured" || coachResponse.status === "no_key") {
    return (
      <View className="rounded-2xl border border-lesLine bg-white/40 p-4 gap-2 items-center">
        <Ionicons name="information-circle-outline" size={22} color="#9E9E9E" />
        <Text className="text-sm font-semibold text-lesMuted">AI coaching is not configured</Text>
        <Text className="text-xs text-lesMuted text-center">{coachResponse.message || "Add LLM settings to the backend to enable."}</Text>
      </View>
    );
  }

  // No data
  if (coachResponse.status === "no_data") {
    return (
      <View className="rounded-2xl border border-lesLine bg-white/40 p-4 gap-2 items-center">
        <Ionicons name="analytics-outline" size={22} color="#9E9E9E" />
        <Text className="text-sm font-semibold text-lesMuted">No coaching data</Text>
        <Text className="text-xs text-lesMuted text-center">{coachResponse.message || "Complete an analysis first."}</Text>
      </View>
    );
  }

  const report = coachResponse.report;
  if (!report) return null;

  return (
    <View className="gap-[22px]">
      {/* Overall summary */}
      <View className="rounded-[26px] bg-lesInk p-5 gap-2">
        <View className="flex-row items-center gap-2">
          <Ionicons name="sparkles" size={16} color="#C8F36A" />
          <Text className="text-sm font-bold text-white">
            {report.practiceType === "group" ? "Group coaching team" : "Solo coaching team"}
          </Text>
        </View>
        <Text className="text-sm text-lesMuted leading-5">{report.overallSummary}</Text>
      </View>

      {report.coordinationNotes.map((note) => (
        <View key={note} className="rounded-2xl border border-[#FFB347]/40 bg-[#FFB347]/10 p-3">
          <Text className="text-xs leading-5 text-lesInk">{note}</Text>
        </View>
      ))}

      {/* Specialist cards */}
      {report.agents.map((agent) => (
        <CoachAgentCard key={agent.agentId} agent={agent} />
      ))}

      {/* Footer */}
      <View className="flex-row items-center justify-center gap-1">
        <Text className="text-[10px] text-lesMuted">
          {report.llmModelUsed ? `Generated with ${report.llmModelUsed}` : "Generated from data (no AI)"}
        </Text>
      </View>
    </View>
  );
}
