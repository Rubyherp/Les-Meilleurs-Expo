import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import type { IntegrationRun } from "@/models/IntegrationRun";

const labels = { completed: "Completed", running: "Running", fallback: "Fallback used", not_configured: "Not configured", failed: "Failed", pending: "Pending" };

export default function IntegrationProvenance({ integrations }: { integrations: IntegrationRun[] }) {
  const [open, setOpen] = useState(false);
  if (!integrations.length) return null;
  return (
    <View className="rounded-2xl border border-lesLine p-4 gap-3">
      <Pressable onPress={() => setOpen((value) => !value)} className="flex-row justify-between">
        <Text className="text-sm font-bold text-lesInk">How this analysis was produced</Text>
        <Text className="text-xs text-lesCoral">{open ? "Hide" : "Show"}</Text>
      </Pressable>
      {open && integrations.map((run, index) => (
        <View key={`${run.provider}-${run.product}-${index}`} className="flex-row items-start gap-2">
          <View className={`mt-1 h-2 w-2 rounded-full ${run.status === "completed" ? "bg-lesLime" : run.status === "failed" ? "bg-lesCoral" : "bg-lesLine"}`} />
          <View className="flex-1">
            <Text className="text-xs font-bold capitalize text-lesInk">{run.provider} · {labels[run.status]}</Text>
            <Text className="text-[10px] text-lesMuted">
              {[run.product.replaceAll("-", " "), run.model, run.latencyMs === null ? null : `${run.latencyMs} ms`].filter(Boolean).join(" · ")}
            </Text>
            {run.fallbackReason ? <Text className="text-[10px] text-lesMuted">{run.fallbackReason.replaceAll("_", " ")}</Text> : null}
          </View>
        </View>
      ))}
    </View>
  );
}
