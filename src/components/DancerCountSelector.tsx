import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  value: number;
  onChange: (value: number) => void;
}

export default function DancerCountSelector({ value, onChange }: Props) {
  const normalizedValue = Math.max(2, Math.min(8, value));

  const update = (nextValue: number) => {
    onChange(Math.max(2, Math.min(8, nextValue)));
  };

  return (
    <View className="flex-row items-center justify-between rounded-2xl border border-lesLine bg-white/60 px-4 py-3">
      <View className="gap-0.5">
        <Text className="font-semibold text-lesInk">Expected dancers</Text>
        <Text className="text-xs text-lesMuted">Used to verify everyone stays visible.</Text>
      </View>
      <View className="flex-row items-center gap-3">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Remove one dancer"
          disabled={normalizedValue <= 2}
          onPress={() => update(normalizedValue - 1)}
          className="h-9 w-9 items-center justify-center rounded-full border border-lesLine bg-white"
          style={{ opacity: normalizedValue <= 2 ? 0.35 : 1 }}
        >
          <Ionicons name="remove" size={18} color="#17171D" />
        </Pressable>
        <Text className="min-w-6 text-center text-lg font-bold text-lesInk">
          {normalizedValue}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Add one dancer"
          disabled={normalizedValue >= 8}
          onPress={() => update(normalizedValue + 1)}
          className="h-9 w-9 items-center justify-center rounded-full border border-lesLine bg-white"
          style={{ opacity: normalizedValue >= 8 ? 0.35 : 1 }}
        >
          <Ionicons name="add" size={18} color="#17171D" />
        </Pressable>
      </View>
    </View>
  );
}
