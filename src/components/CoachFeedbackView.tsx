import { View, Text, ActivityIndicator, Pressable } from "react-native";
import type { CoachReport, CoachReportAgent } from "../models/CoachReport";

interface Props {
  report: CoachReport | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

function severityColor(severity: string): string {
  switch (severity) {
    case "high":
      return "text-lesCoral";
    case "medium":
      return "text-lesInk/60";
    default:
      return "text-lesMuted";
  }
}

function AgentCard({ agent }: { agent: CoachReportAgent }) {
  return (
    <View className="p-4 bg-white/70 border border-lesLine rounded-2xl gap-3">
      <Text className="text-sm font-bold text-lesInk uppercase tracking-wide">
        {agent.agentName}
      </Text>
      <Text className="text-sm text-lesInk/80 leading-5">{agent.summary}</Text>

      {agent.strengths.length > 0 && (
        <View className="gap-1.5">
          {agent.strengths.map((s, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Text className="text-lesLime text-base leading-5">+</Text>
              <Text className="text-sm text-lesInk flex-1">{s}</Text>
            </View>
          ))}
        </View>
      )}

      {agent.issues.length > 0 && (
        <View className="gap-1.5">
          {agent.issues.map((iss, i) => (
            <View key={i} className="flex-row items-start gap-2">
              <Text className={`text-base leading-5 ${severityColor(iss.severity)}`}>
                {iss.severity === "high" ? "!" : iss.severity === "medium" ? "~" : "-"}
              </Text>
              <Text className="text-sm text-lesInk flex-1">{iss.description}</Text>
            </View>
          ))}
        </View>
      )}

      {agent.suggestions.length > 0 && (
        <View className="gap-1.5 pt-1">
          <Text className="text-xs font-bold text-lesMuted uppercase">Try this</Text>
          {agent.suggestions.map((sg, i) => (
            <Text key={i} className="text-sm text-lesInk/90 leading-5">
              {"\u2192"} {sg}
            </Text>
          ))}
        </View>
      )}

      <View className="flex-row items-center gap-2 pt-1">
        <View className="h-1.5 flex-1 bg-lesLine rounded-full overflow-hidden">
          <View
            className="h-full bg-lesCoral rounded-full"
            style={{ width: `${Math.round(agent.confidence * 100)}%` }}
          />
        </View>
        <Text className="text-xs text-lesMuted">
          {Math.round(agent.confidence * 100)}%
        </Text>
      </View>
    </View>
  );
}

function SkeletonCard() {
  return (
    <View className="p-4 bg-white/70 border border-lesLine rounded-2xl gap-3">
      <View className="h-4 w-24 bg-lesLine rounded" />
      <View className="h-3 w-full bg-lesLine rounded" />
      <View className="h-3 w-5/6 bg-lesLine rounded" />
      <View className="h-3 w-2/3 bg-lesLine rounded" />
      <View className="h-8 w-full bg-lesLine rounded" />
    </View>
  );
}

export default function CoachFeedbackView({ report, loading, error, onRetry }: Props) {
  if (loading) {
    return (
      <View className="gap-4">
        <View className="flex-row items-center gap-2">
          <ActivityIndicator size="small" color="#17171D" />
          <Text className="text-sm text-lesInk">Analyzing your practice...</Text>
        </View>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </View>
    );
  }

  if (error) {
    return (
      <View className="p-4 bg-white/70 border border-lesLine rounded-2xl gap-3">
        <Text className="text-sm font-bold text-lesCoral">AI Coaching unavailable</Text>
        <Text className="text-sm text-lesMuted">{error}</Text>
        {onRetry && (
          <Pressable
            onPress={onRetry}
            className="self-start px-4 py-2 bg-lesInk rounded-lg"
          >
            <Text className="text-sm font-semibold text-lesBackground">Try again</Text>
          </Pressable>
        )}
      </View>
    );
  }

  if (!report) {
    return (
      <View className="p-4 bg-white/70 border border-lesLine rounded-2xl">
        <Text className="text-sm text-lesMuted">
          AI coaching not available for this session.
        </Text>
      </View>
    );
  }

  return (
    <View className="gap-4">
      <View className="gap-1">
        <Text className="text-lg font-bold text-lesInk">AI Coaching</Text>
        <Text className="text-sm text-lesInk/70 leading-5">{report.overallSummary}</Text>
      </View>

      {report.agents.map((agent, i) => (
        <AgentCard key={i} agent={agent} />
      ))}
    </View>
  );
}
