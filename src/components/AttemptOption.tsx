import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  icon: string;
  tint: string;
  onPress: () => void;
}

export default function AttemptOption({ title, icon, tint, onPress }: Props) {
  return (
    <Pressable
      onPress={onPress}
      className="flex-1 bg-white/70 border border-lesLine rounded-2xl items-center justify-center gap-2.5 min-h-[112px]"
      style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
    >
      <Ionicons name={icon as any} size={24} color={tint} />
      <Text className="text-sm font-bold text-lesInk">{title}</Text>
    </Pressable>
  );
}
