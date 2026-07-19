import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  detail: string;
  icon: string;
  tint: string;
}

export default function MediaImportCard({ title, detail, icon, tint }: Props) {
  return (
    <View className="p-6 bg-white/70 border border-lesLine rounded-3xl items-center gap-2.5 min-h-[154px] justify-center">
      <Ionicons name={icon as any} size={24} color={tint} />
      <Text className="font-semibold text-lesInk">{title}</Text>
      <Text className="text-sm text-lesMuted text-center">{detail}</Text>
    </View>
  );
}
