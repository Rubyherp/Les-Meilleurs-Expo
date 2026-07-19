import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  onAction: () => void;
}

export default function EmptyStateCard({ onAction }: Props) {
  return (
    <View className="p-5 bg-lesLime/40 border border-lesInk/10 rounded-3xl gap-4">
      <Ionicons name="sparkles" size={24} color="#FF5C5C" />
      <Text className="text-lg font-bold text-lesInk">
        Your first take starts here.
      </Text>
      <Text className="text-base text-lesMuted">
        Bring a trend, record your version, and get clear next steps.
      </Text>
      <Pressable
        onPress={onAction}
        className="self-start border border-lesInk rounded-lg px-4 py-2"
        style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
      >
        <Text className="font-semibold text-lesInk">Start practicing</Text>
      </Pressable>
    </View>
  );
}
