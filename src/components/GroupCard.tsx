import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  name: string;
  detail: string;
  isEmpty?: boolean;
  onPress?: () => void;
}

function GroupCardContent({ name, detail, isEmpty }: Props) {
  return (
    <View className="flex-row items-center p-3.5 bg-white/60 border border-lesLine rounded-2xl gap-3.5">
      <View
        className="w-[54px] h-[54px] rounded-2xl items-center justify-center"
        style={{ backgroundColor: isEmpty ? "#DAD6CC" : "#17171D" }}
      >
        <Ionicons
          name={isEmpty ? "add" : "people"}
          size={20}
          color={isEmpty ? "#17171D" : "#C8F36A"}
        />
      </View>
      <View className="flex-1 gap-1">
        <Text className="font-semibold text-lesInk">{name}</Text>
        <Text className="text-sm text-lesMuted">{detail}</Text>
      </View>
    </View>
  );
}

export default function GroupCard({ name, detail, isEmpty = false, onPress }: Props) {
  if (!onPress) {
    return <GroupCardContent name={name} detail={detail} isEmpty={isEmpty} />;
  }

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        opacity: pressed ? 0.7 : 1,
        transform: [{ scale: pressed ? 0.985 : 1 }],
      })}
      accessibilityRole="button"
      accessibilityLabel={`${name}, ${detail}`}
    >
      <GroupCardContent name={name} detail={detail} isEmpty={isEmpty} />
    </Pressable>
  );
}
