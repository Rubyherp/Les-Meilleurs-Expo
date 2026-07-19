import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import ProgressRow from "./ProgressRow";

interface Props {
  session: { title: string; id: string };
  phase: string;
  errorMessage?: string;
  onRetry: () => void;
  onClose: () => void;
}

export default function ProcessingView({
  session,
  phase,
  errorMessage,
  onRetry,
  onClose,
}: Props) {
  const isFailed = phase === "failed";
  const phaseOrder = ["preparing", "uploading", "analyzing"];
  const currentIndex = phaseOrder.indexOf(phase);
  const trimProgress =
    phase === "analyzing" ? 0.82 : phase === "uploading" ? 0.52 : 0.24;

  return (
    <View className="flex-1 bg-lesBackground items-center justify-center gap-[26px] px-5">
      <View className="w-[150px] h-[150px] items-center justify-center">
        <View className="absolute w-full h-full rounded-full border-[12px] border-lesLine" />
        {!isFailed && (
          <View
            className="absolute w-full h-full rounded-full border-[12px] border-l-transparent border-b-transparent"
            style={{
              borderColor: "#FF5C5C",
              borderTopColor: "#FF5C5C",
              borderRightColor: "#FF5C5C",
              borderBottomColor: "transparent",
              borderLeftColor: "transparent",
              transform: [{ rotate: `${trimProgress * 360 - 90}deg` }],
            }}
          />
        )}
        <Ionicons
          name={isFailed ? "alert-circle" : "body"}
          size={34}
          color="#17171D"
        />
      </View>

      <View className="items-center gap-2 px-7">
        <Text className="text-2xl font-bold text-lesInk">
          {isFailed ? "Almost there" : "Preparing your practice"}
        </Text>
        <Text className="text-base text-lesMuted text-center">
          {errorMessage || phase}
        </Text>
      </View>

      <View className="p-5 bg-white/70 border border-lesLine rounded-[22px] w-full max-w-[360px] gap-3.5">
        <ProgressRow
          title="Preparing videos"
          isComplete={currentIndex > 0 && !isFailed}
          isCurrent={currentIndex === 0}
        />
        <ProgressRow
          title="Comparing movement"
          isComplete={phase === "completed"}
          isCurrent={currentIndex === 2}
        />
        <ProgressRow
          title="Writing suggestions"
          isComplete={phase === "completed"}
          isCurrent={false}
        />
      </View>

      {isFailed ? (
        <Pressable
          onPress={onRetry}
          className="bg-lesCoral rounded-lg px-6 py-3"
          style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
        >
          <Text className="font-semibold text-white">Try again</Text>
        </Pressable>
      ) : (
        <Text className="text-xs text-lesMuted text-center px-8">
          You can leave this screen. Your take stays on this device until you
          choose to share it.
        </Text>
      )}

      <Pressable
        onPress={onClose}
        style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
      >
        <Text className="text-sm font-semibold text-lesInk">Back to Practice</Text>
      </Pressable>
    </View>
  );
}
