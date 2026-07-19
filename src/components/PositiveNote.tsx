import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  text: string;
}

export default function PositiveNote({ text }: Props) {
  return (
    <View className="flex-row items-center p-3.5 bg-lesLime/50 rounded-2xl gap-2">
      <Ionicons name="checkmark" size={18} color="#17171D" />
      <Text className="text-sm font-semibold text-lesInk">{text}</Text>
    </View>
  );
}
