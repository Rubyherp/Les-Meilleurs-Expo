import { Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  icon: string;
  tint: string;
  onPress?: () => void;
}

export default function ActionTile({ title, icon, tint, onPress }: Props) {
  return (
    <Pressable
      className="flex-1 p-4 rounded-2xl min-h-[88px] justify-end gap-3"
      style={({ pressed }) => ({
        backgroundColor: tint,
        transform: [{ scale: pressed ? 0.98 : 1 }],
      })}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !onPress }}
    >
      <Ionicons name={icon as any} size={20} color="#17171D" />
      <Text className="text-sm font-bold text-lesInk">{title}</Text>
    </Pressable>
  );
}
