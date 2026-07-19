import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  session: {
    id: string;
    title: string;
    participantIDs: string[];
    duration: number;
  };
}

export default function SessionCard({ session }: Props) {
  const isSolo = session.participantIDs.length === 0;

  return (
    <View className="flex-row items-center p-3.5 bg-white/60 border border-lesLine rounded-[22px] gap-3.5">
      <View className="w-[66px] h-[66px] bg-lesInk rounded-2xl items-center justify-center">
        <Ionicons name={isSolo ? "body" : "people"} size={24} color="#C8F36A" />
      </View>
      <View className="flex-1 gap-1.5">
        <Text className="font-semibold text-lesInk">{session.title}</Text>
        <Text className="text-sm text-lesMuted">
          {isSolo ? "Solo practice" : "Group choreography · 3 dancers"}
        </Text>
        <Text className="text-xs font-semibold text-lesCoral">
          Draft · {session.duration} sec
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color="#747475" />
    </View>
  );
}
