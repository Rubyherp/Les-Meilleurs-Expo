import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  count: number;
}

export default function GroupSyncCard({ count }: Props) {
  return (
    <View className="flex-row items-center p-4 bg-lesLime/40 rounded-2xl gap-3.5">
      <View className="w-12 h-12 bg-lesLime rounded-full items-center justify-center">
        <Ionicons name="people" size={20} color="#17171D" />
      </View>
      <View className="flex-1 gap-1">
        <Text className="font-semibold text-lesInk">Group rhythm signal</Text>
        <Text className="text-sm text-lesMuted">
          {count} dancers · spacing changes in the middle section
        </Text>
      </View>
    </View>
  );
}
