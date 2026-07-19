import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  isComplete: boolean;
  isCurrent: boolean;
}

export default function ProgressRow({ title, isComplete, isCurrent }: Props) {
  const icon = isComplete
    ? "checkmark-circle"
    : isCurrent
      ? "sync-circle"
      : "ellipse-outline";
  const color = isComplete ? "#C8F36A" : isCurrent ? "#FF5C5C" : "#747475";

  return (
    <View className="flex-row items-center gap-3">
      <Ionicons name={icon as any} size={20} color={color} />
      <Text
        className={`text-sm ${isComplete || isCurrent ? "font-semibold" : ""} text-lesInk`}
      >
        {title}
      </Text>
    </View>
  );
}
