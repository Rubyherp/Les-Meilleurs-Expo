import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { toHexWithAlpha } from "../utils/color";

interface Props {
  text: string;
  icon: string;
  tint?: string;
}

export default function InlineStatus({ text, icon, tint = "#17171D" }: Props) {
  return (
    <View
      className="flex-row items-center self-start px-3.5 py-2.5 rounded-full gap-2"
      style={{ backgroundColor: toHexWithAlpha(tint, "8C") }}
    >
      <Ionicons name={icon as any} size={16} color="#17171D" />
      <Text className="text-sm font-semibold text-lesInk">{text}</Text>
    </View>
  );
}
