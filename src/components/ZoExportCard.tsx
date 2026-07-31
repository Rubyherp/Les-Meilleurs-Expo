import { useRef, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text, View } from "react-native";
import { exportToZo } from "@/services/zoApi";
import type { ZoExportResponse } from "@/models/ZoExport";

export default function ZoExportCard({ sessionId }: { sessionId?: string }) {
  const [visibility, setVisibility] = useState<"private" | "unlisted">("private");
  const [result, setResult] = useState<ZoExportResponse | null>(null);
  const [remindTomorrow, setRemindTomorrow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inFlight = useRef(false);
  if (!sessionId) return null;
  const submit = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setLoading(true); setError(null);
    try {
      const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
      setResult(await exportToZo(sessionId, {
        visibility,
        schedule_reminder: remindTomorrow,
        ...(remindTomorrow ? {
          reminder_at: tomorrow.toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        } : {}),
      }));
    }
    catch (value) { setError(value instanceof Error ? value.message : "Zo export failed."); }
    finally { inFlight.current = false; setLoading(false); }
  };
  return (
    <View className="rounded-[26px] border border-lesLine bg-white/50 p-5 gap-3">
      <Text className="text-lg font-bold text-lesInk">Save your practice plan</Text>
      <Text className="text-xs text-lesMuted">Zo writes and verifies a compact report—never your raw video.</Text>
      <View className="flex-row gap-2">
        {(["private", "unlisted"] as const).map((value) => <Pressable key={value} onPress={() => setVisibility(value)} className={`rounded-lg px-3 py-2 ${visibility === value ? "bg-lesInk" : "bg-lesLine"}`}><Text className={`text-xs font-bold ${visibility === value ? "text-white" : "text-lesInk"}`}>{value}</Text></Pressable>)}
      </View>
      <Pressable onPress={() => setRemindTomorrow((value) => !value)} className="flex-row items-center gap-2">
        <View className={`h-5 w-5 rounded border border-lesInk ${remindTomorrow ? "bg-lesLime" : "bg-transparent"}`} />
        <Text className="text-xs text-lesInk">Remind me to practice again tomorrow</Text>
      </Pressable>
      <Pressable disabled={loading} onPress={submit} className="rounded-lg bg-lesCoral py-3 items-center">
        {loading ? <ActivityIndicator color="white" /> : <Text className="font-bold text-white">Save practice report to Zo</Text>}
      </Pressable>
      {error ? <Text className="text-xs text-lesCoral">{error}</Text> : null}
      {result?.status === "completed" ? <View className="gap-1">
        <Text className="text-xs font-bold text-lesInk">Saved and verified in Zo</Text>
        {result.message ? <Text className="text-xs text-lesMuted">{result.message}</Text> : null}
        {result.file_path ? <Text selectable className="text-xs text-lesInk">{result.file_path}</Text> : null}
        {result.url ? <Pressable onPress={() => Linking.openURL(result.url!)}><Text className="text-xs text-lesCoral">Open report</Text></Pressable> : null}
      </View> : null}
      {result?.status === "failed" ? <View className="gap-1">
        <Text className="text-xs font-bold text-lesCoral">Zo did not save the report</Text>
        <Text className="text-xs text-lesMuted">{result.message || "Tap save to retry."}</Text>
        <Text className="text-xs text-lesMuted">Tap save to retry.</Text>
      </View> : null}
      {result?.reminder_id ? <Text className="text-xs text-lesMuted">Reminder scheduled</Text> : null}
      {result?.status === "not_configured" ? <Text className="text-xs text-lesMuted">Zo is not configured on the backend.</Text> : null}
    </View>
  );
}
