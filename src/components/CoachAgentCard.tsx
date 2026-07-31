import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { CoachAgent } from "@/models/CoachReport";

interface Props {
  agent: CoachAgent;
}

const PHASE_COLORS: Record<number, { bg: string; badge: string; accent: string }> = {
  1: { bg: "bg-green-50", badge: "bg-[#C8F36A]/20", accent: "#78A520" },
  2: { bg: "bg-amber-50", badge: "bg-[#FFB347]/20", accent: "#D97706" },
  3: { bg: "bg-blue-50", badge: "bg-[#4A90D9]/20", accent: "#4A90D9" },
  4: { bg: "bg-purple-50", badge: "bg-purple-500/15", accent: "#8B5CF6" },
};

const SEVERITY_COLORS: Record<string, string> = {
  high: "border-l-[#FF5C5C]",
  medium: "border-l-[#FFB347]",
  low: "border-l-[#9E9E9E]",
};

function formatEvidenceValue(value: number | string, unit: string | null): string {
  if (typeof value === "number") {
    if (unit === "ratio") return `${Math.round(value * 100)}%`;
    if (unit === "seconds") return `${value.toFixed(2)}s`;
  }
  return unit && unit !== "ratio" ? `${value} ${unit}` : String(value);
}

export default function CoachAgentCard({ agent }: Props) {
  const colors = PHASE_COLORS[agent.agentId] ?? { bg: "bg-gray-50", badge: "bg-gray-200", accent: "#9E9E9E" };

  if (!agent.available) {
    return (
      <View className="rounded-2xl border border-lesLine bg-white/40 p-4 gap-2 opacity-60">
        <View className="flex-row items-center gap-2">
          <View className={`rounded-full px-2 py-0.5 ${colors.badge}`}>
            <Text className="text-xs font-bold" style={{ color: colors.accent }}>Agent {agent.agentId}</Text>
          </View>
          <Text className="text-sm font-semibold text-lesMuted">{agent.name}</Text>
        </View>
        <Text className="text-xs text-lesMuted">{agent.summary}</Text>
      </View>
    );
  }

  return (
    <View className="rounded-2xl border border-lesLine bg-white/70 p-4 gap-3">
      {/* Header */}
      <View className="flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          <View className={`rounded-full px-2 py-0.5 ${colors.badge}`}>
            <Text className="text-xs font-bold" style={{ color: colors.accent }}>Agent {agent.agentId}</Text>
          </View>
          <Text className="text-sm font-semibold text-lesInk">{agent.name}</Text>
        </View>
        <View className="rounded-full bg-lesInk/10 px-2 py-0.5">
          <Text className="text-[10px] font-medium text-lesMuted uppercase">
            {agent.source === "gmi" ? "GMI" : agent.source === "llm" ? "AI" : agent.source === "error" ? "Error" : "Data-driven"}
          </Text>
        </View>
      </View>

      {/* Summary */}
      <Text className="text-sm text-lesInk leading-5">{agent.summary}</Text>

      {/* Strengths */}
      {agent.strengths.length > 0 && (
        <View className="gap-1">
          {agent.strengths.map((s, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Ionicons name="checkmark-circle" size={14} color={colors.accent} style={{ marginTop: 2 }} />
              <Text className="text-xs text-lesInk flex-1">{s}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Issues */}
      {agent.issues.length > 0 && (
        <View className="gap-1">
          {agent.issues.map((issue, i) => (
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
      {agent.suggestions.length > 0 && (
        <View className="gap-1">
          {agent.suggestions.map((s, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Ionicons name="bulb-outline" size={14} color="#4A90D9" style={{ marginTop: 2 }} />
              <Text className="text-xs text-lesInk flex-1">{s}</Text>
            </View>
          ))}
        </View>
      )}

      {agent.evidence.length > 0 && (
        <View className="flex-row flex-wrap gap-2 border-t border-lesLine pt-2">
          {agent.evidence.map((item) => (
            <View key={item.metric} className="rounded-full bg-lesInk/5 px-2.5 py-1">
              <Text className="text-[10px] text-lesMuted">
                {item.metric.replaceAll("_", " ")} · {formatEvidenceValue(item.value, item.unit)}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Confidence bar */}
      <View className="h-1 rounded-full bg-lesLine overflow-hidden">
        <View 
          className="h-full rounded-full" 
          style={{ width: `${Math.round(agent.confidence * 100)}%`, backgroundColor: colors.accent }} 
        />
      </View>
    </View>
  );
}
