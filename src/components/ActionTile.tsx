import { Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  icon: string;
  tint: string;
}

export default function ActionTile({ title, icon, tint }: Props) {
  return (
    <Pressable
      className="flex-1 p-4 rounded-2xl min-h-[88px] justify-end gap-3"
      style={({ pressed }) => ({
        backgroundColor: tint,
        transform: [{ scale: pressed ? 0.98 : 1 }],
      })}
    >
      <Ionicons name={icon as any} size={20} color="#17171D" />
      <Text className="text-sm font-bold text-lesInk">{title}</Text>
    </Pressable>
  );
}
