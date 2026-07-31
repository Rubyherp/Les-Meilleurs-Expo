import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { IntegrationRun } from "@/models/IntegrationRun";

const labels = { completed: "Completed", running: "Running", fallback: "Fallback used", not_configured: "Not configured", failed: "Failed", pending: "Pending" };

function presentation(run: IntegrationRun) {
  if (run.product === "analysis-runtime" && run.fallbackReason === "local_analysis_completed") {
    return {
      title: "Local analysis · Completed",
      detail: "GMI Compute was not enabled; analysis ran locally.",
      showFallbackReason: false,
      color: "#27864A",
      icon: "checkmark-circle" as const,
    };
  }

  const provider = run.provider === "gmi"
    ? run.product === "serverless-inference-audit" ? "GMI Inference" : "GMI Compute"
    : run.provider;
  const succeeded = run.status === "completed";
  const failed = run.status === "failed";
  return {
    title: `${provider} · ${labels[run.status]}`,
    detail: null,
    showFallbackReason: true,
    color: succeeded ? "#27864A" : failed ? "#FF5C5C" : "#9E9E9E",
    icon: succeeded ? "checkmark-circle" as const : failed ? "close-circle" as const : "ellipse" as const,
  };
}

export default function IntegrationProvenance({ integrations }: { integrations: IntegrationRun[] }) {
  const [open, setOpen] = useState(false);
  if (!integrations.length) return null;
  return (
    <View className="rounded-2xl border border-lesLine p-4 gap-3">
      <Pressable onPress={() => setOpen((value) => !value)} className="flex-row justify-between">
        <Text className="text-sm font-bold text-lesInk">How this analysis was produced</Text>
        <Text className="text-xs text-lesCoral">{open ? "Hide" : "Show"}</Text>
      </Pressable>
      {open && integrations.map((run, index) => {
        const item = presentation(run);
        return (
        <View key={`${run.provider}-${run.product}-${index}`} className="flex-row items-start gap-2">
          <Ionicons name={item.icon} size={15} color={item.color} />
          <View className="flex-1">
            <Text className="text-xs font-bold capitalize text-lesInk">{item.title}</Text>
            <Text className="text-[10px] text-lesMuted">
              {[run.product.replaceAll("-", " "), run.model, run.latencyMs === null ? null : `${run.latencyMs} ms`].filter(Boolean).join(" · ")}
            </Text>
            {item.detail ? <Text className="text-[10px] text-lesMuted">{item.detail}</Text> : null}
            {item.showFallbackReason && run.fallbackReason ? <Text className="text-[10px] text-lesMuted">{run.fallbackReason.replaceAll("_", " ")}</Text> : null}
          </View>
        </View>
      )})}
    </View>
  );
}
