import { View, Text } from "react-native";

interface Props {
  eyebrow: string;
  title: string;
  subtitle: string;
}

export default function PageHeader({ eyebrow, title, subtitle }: Props) {
  return (
    <View className="gap-2">
      <Text className="text-xs font-bold tracking-[2.1px] text-lesCoral uppercase">
        {eyebrow}
      </Text>
      <Text className="text-[36px] font-bold text-lesInk leading-[40px]">
        {title}
      </Text>
      <Text className="text-base text-lesMuted">{subtitle}</Text>
    </View>
  );
}
