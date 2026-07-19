import { View, Text, Pressable } from "react-native";
import { DanceIssue } from "../models/DanceIssue";
import { formatTimestamp } from "../utils/format";

interface Props {
  issue: DanceIssue;
  onReplay: () => void;
}

export default function SuggestionCard({ issue, onReplay }: Props) {
  return (
    <View className="p-[18px] bg-white/70 border border-lesLine rounded-2xl gap-2.5">
      <View className="flex-row justify-between">
        <Text className="text-xs font-bold text-lesCoral capitalize">
          {issue.category}
        </Text>
        <Text className="text-xs font-semibold text-lesMuted font-mono">
          {formatTimestamp(issue.timestamp)}
        </Text>
      </View>
      <Text className="font-semibold text-lesInk">{issue.message}</Text>
      <Pressable
        onPress={onReplay}
        style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
      >
        <Text className="text-sm font-bold text-lesInk">Replay this moment</Text>
      </Pressable>
    </View>
  );
}
