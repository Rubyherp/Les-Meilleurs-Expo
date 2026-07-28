import { Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  title: string;
  enabled: boolean;
  onPress?: () => void;
}

export default function PrimaryButton({ title, enabled, onPress }: Props) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!enabled || !onPress}
      className={`flex-row items-center p-[18px] rounded-2xl ${
        enabled ? "bg-lesInk" : "bg-lesLine"
      }`}
      style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
    >
      <Text
        className={`font-semibold flex-1 ${
          enabled ? "text-lesBackground" : "text-lesMuted"
        }`}
      >
        {title}
      </Text>
      <Ionicons
        name="arrow-forward"
        size={20}
        color={enabled ? "#F7F4EE" : "#747475"}
      />
    </Pressable>
  );
}
