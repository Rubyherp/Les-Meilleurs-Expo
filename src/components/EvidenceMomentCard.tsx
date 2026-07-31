import { Pressable, Text, View } from "react-native";
import type { EvidenceMoment } from "@/models/EvidenceMoment";

export default function EvidenceMomentCard({ moment, onViewMoment }: { moment: EvidenceMoment; onViewMoment: (seconds: number) => void }) {
  const time = `${Math.floor(moment.primaryTimestampSeconds / 60)}:${Math.floor(moment.primaryTimestampSeconds % 60).toString().padStart(2, "0")}`;
  return (
    <View className="rounded-2xl border border-lesLine bg-white/60 p-4 gap-2">
      <View className="flex-row justify-between">
        <Text className="text-xs font-bold uppercase text-lesCoral">{moment.category} · {moment.severity}</Text>
        <Text className="text-xs font-bold text-lesInk">{time}</Text>
      </View>
      <Text className="text-sm text-lesInk">{moment.visualReview?.summary ?? moment.deterministicReason}</Text>
      {moment.visualReview?.limitations?.[0] ? <Text className="text-xs text-lesMuted">Limit: {moment.visualReview.limitations[0]}</Text> : null}
      {moment.visualReview ? <Text className="text-[10px] text-lesMuted">Agnes confidence {Math.round(moment.visualReview.confidence * 100)}%</Text> : null}
      <Pressable onPress={() => onViewMoment(moment.primaryTimestampSeconds)} className="self-start rounded-lg bg-lesInk px-3 py-2">
        <Text className="text-xs font-bold text-white">View moment</Text>
      </Pressable>
    </View>
  );
}
