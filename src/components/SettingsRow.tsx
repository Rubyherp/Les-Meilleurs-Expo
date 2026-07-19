import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  icon: string;
  title: string;
  detail: string;
}

export default function SettingsRow({ icon, title, detail }: Props) {
  return (
    <View className="flex-row items-center gap-3.5 py-3.5">
      <Ionicons name={icon as any} size={20} color="#FF5C5C" className="w-6" />
      <View className="flex-1 gap-1">
        <Text className="text-sm font-semibold text-lesInk">{title}</Text>
        <Text className="text-xs text-lesMuted">{detail}</Text>
      </View>
    </View>
  );
}
