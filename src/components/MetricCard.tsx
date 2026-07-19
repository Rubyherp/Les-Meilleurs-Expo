import { View, Text } from "react-native";

interface Props {
  value: string;
  label: string;
  tint?: string;
}

export default function MetricCard({ value, label, tint = "#17171D" }: Props) {
  return (
    <View className="flex-1 p-3.5 bg-white/60 border border-lesLine rounded-2xl gap-2">
      <Text className="text-2xl font-bold" style={{ color: tint }}>
        {value}
      </Text>
      <Text className="text-xs font-semibold text-lesMuted">{label}</Text>
    </View>
  );
}
