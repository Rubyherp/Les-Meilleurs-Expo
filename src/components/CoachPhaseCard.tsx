import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { CoachPhase } from "@/models/CoachReport";

interface Props {
  phase: CoachPhase;
}

const PHASE_COLORS: Record<number, { bg: string; badge: string; accent: string }> = {
  2: { bg: "bg-green-50", badge: "bg-[#C8F36A]/20", accent: "#C8F36A" },
  3: { bg: "bg-amber-50", badge: "bg-[#FFB347]/20", accent: "#FFB347" },
  4: { bg: "bg-blue-50", badge: "bg-[#4A90D9]/20", accent: "#4A90D9" },
  5: { bg: "bg-red-50", badge: "bg-[#FF5C5C]/20", accent: "#FF5C5C" },
};

const SEVERITY_COLORS: Record<string, string> = {
  high: "border-l-[#FF5C5C]",
  medium: "border-l-[#FFB347]",
  low: "border-l-[#9E9E9E]",
};

export default function CoachPhaseCard({ phase }: Props) {
  const colors = PHASE_COLORS[phase.phase] ?? { bg: "bg-gray-50", badge: "bg-gray-200", accent: "#9E9E9E" };

  if (!phase.available) {
    return (
      <View className="rounded-2xl border border-lesLine bg-white/40 p-4 gap-2 opacity-60">
        <View className="flex-row items-center gap-2">
          <View className={`rounded-full px-2 py-0.5 ${colors.badge}`}>
            <Text className="text-xs font-bold" style={{ color: colors.accent }}>Phase {phase.phase}</Text>
          </View>
          <Text className="text-sm font-semibold text-lesMuted">{phase.name}</Text>
        </View>
        <Text className="text-xs text-lesMuted">{phase.summary}</Text>
      </View>
    );
  }

  return (
    <View className="rounded-2xl border border-lesLine bg-white/70 p-4 gap-3">
      {/* Header */}
      <View className="flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          <View className={`rounded-full px-2 py-0.5 ${colors.badge}`}>
            <Text className="text-xs font-bold" style={{ color: colors.accent }}>Phase {phase.phase}</Text>
          </View>
          <Text className="text-sm font-semibold text-lesInk">{phase.name}</Text>
        </View>
        <View className="rounded-full bg-lesInk/10 px-2 py-0.5">
          <Text className="text-[10px] font-medium text-lesMuted uppercase">
            {phase.source === "llm" ? "AI" : phase.source === "error" ? "Error" : "Data-driven"}
          </Text>
        </View>
      </View>

      {/* Summary */}
      <Text className="text-sm text-lesInk leading-5">{phase.summary}</Text>

      {/* Strengths */}
      {phase.strengths.length > 0 && (
        <View className="gap-1">
          {phase.strengths.map((s, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Ionicons name="checkmark-circle" size={14} color={colors.accent} style={{ marginTop: 2 }} />
              <Text className="text-xs text-lesInk flex-1">{s}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Issues */}
      {phase.issues.length > 0 && (
        <View className="gap-1">
          {phase.issues.map((issue, i) => (
            <View key={i} className={`rounded-lg border-l-2 bg-white/50 p-2 ${SEVERITY_COLORS[issue.severity] ?? "border-l-[#9E9E9E]"}`}>
              <View className="flex-row items-center justify-between">
                <Text className="text-xs font-medium text-lesInk flex-1">{issue.description}</Text>
                <Text className="text-[10px] uppercase font-bold ml-2" style={{ color: issue.severity === "high" ? "#FF5C5C" : issue.severity === "medium" ? "#FFB347" : "#9E9E9E" }}>
                  {issue.severity}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Suggestions */}
      {phase.suggestions.length > 0 && (
        <View className="gap-1">
          {phase.suggestions.map((s, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Ionicons name="bulb-outline" size={14} color="#4A90D9" style={{ marginTop: 2 }} />
              <Text className="text-xs text-lesInk flex-1">{s}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Confidence bar */}
      <View className="h-1 rounded-full bg-lesLine overflow-hidden">
        <View 
          className="h-full rounded-full" 
          style={{ width: `${Math.round(phase.confidence * 100)}%`, backgroundColor: colors.accent }} 
        />
      </View>
    </View>
  );
}
