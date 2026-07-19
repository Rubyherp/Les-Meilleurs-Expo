import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  detail: string;
}

export default function TipCard({ title, detail }: Props) {
  return (
    <View className="flex-row p-4 bg-white/60 border border-lesLine rounded-2xl gap-3">
      <Ionicons name="bulb" size={20} color="#FF5C5C" />
      <View className="flex-1 gap-1">
        <Text className="text-sm font-bold text-lesInk">{title}</Text>
        <Text className="text-xs text-lesMuted">{detail}</Text>
      </View>
    </View>
  );
}
