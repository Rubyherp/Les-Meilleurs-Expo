import { View, Text } from "react-native";
import { Video, ResizeMode } from "expo-av";
import { formatTimestamp } from "../utils/format";

interface Props {
  referenceSource: any;
  attemptSource: any;
  selectedTimestamp: number | null;
}

export default function ComparisonCard({
  referenceSource,
  attemptSource,
  selectedTimestamp,
}: Props) {
  return (
    <View className="gap-3.5">
      <View className="flex-row justify-between items-center">
        <Text className="text-lg font-bold text-lesInk">Compare videos</Text>
        <Text className="text-xs font-semibold text-lesCoral">
          {selectedTimestamp !== null ? formatTimestamp(selectedTimestamp) : "Side by side"}
        </Text>
      </View>
      <View className="flex-row gap-2.5">
        <View className="flex-1 rounded-2xl overflow-hidden min-h-[160px]">
          <Video
            source={referenceSource}
            style={{ width: "100%", height: 160 }}
            resizeMode={ResizeMode.COVER}
            isMuted
            shouldPlay
            isLooping
          />
          <Text className="absolute bottom-3 left-3 text-[10px] font-bold tracking-[1.1px] text-white/85">
            REFERENCE
          </Text>
        </View>
        <View className="flex-1 rounded-2xl overflow-hidden min-h-[160px]">
          <Video
            source={attemptSource}
            style={{ width: "100%", height: 160 }}
            resizeMode={ResizeMode.COVER}
            isMuted
            shouldPlay
            isLooping
          />
          <Text className="absolute bottom-3 left-3 text-[10px] font-bold tracking-[1.1px] text-white/85">
            YOUR TAKE
          </Text>
        </View>
      </View>
      <Text className="text-xs text-lesMuted">
        Demo mode uses your bundled clips: reference and your attempt side by
        side.
      </Text>
    </View>
  );
}
