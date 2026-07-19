import { Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import PageHeader from "@/components/PageHeader";

interface ModeCardProps {
  number: string;
  title: string;
  detail: string;
  icon: string;
  tint: string;
  onPress: () => void;
}

function ModeCard({ number, title, detail, icon, tint, onPress }: ModeCardProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${number}: ${title}`}
      onPress={onPress}
      className="overflow-hidden rounded-3xl border border-lesLine bg-white/75"
      style={({ pressed }) => ({
        transform: [{ scale: pressed ? 0.985 : 1 }],
      })}
    >
      <View className="flex-row items-start justify-between p-5 pb-3">
        <View
          className="h-12 w-12 items-center justify-center rounded-2xl"
          style={{ backgroundColor: tint }}
        >
          <Ionicons name={icon as any} size={24} color="#17171D" />
        </View>
        <View className="rounded-full bg-lesInk px-3 py-1.5">
          <Text className="text-[11px] font-bold tracking-[1.5px] text-lesBackground">
            {number}
          </Text>
        </View>
      </View>
      <View className="gap-1 px-5 pb-5">
        <Text className="text-xl font-bold text-lesInk">{title}</Text>
        <Text className="text-sm leading-5 text-lesMuted">{detail}</Text>
      </View>
      <View className="flex-row items-center justify-between border-t border-lesLine px-5 py-3.5">
        <Text className="text-xs font-bold uppercase tracking-[1.2px] text-lesCoral">
          Start here
        </Text>
        <Ionicons name="arrow-forward" size={18} color="#FF5C5C" />
      </View>
    </Pressable>
  );
}

export default function CreateSessionScreen() {
  const router = useRouter();

  return (
    <ScrollView className="flex-1 bg-lesBackground" contentContainerClassName="pb-8">
      <View className="gap-7 p-5">
        <View className="flex-row items-center justify-between">
          <View className="flex-row items-center gap-2">
            <View className="h-2.5 w-2.5 rounded-full bg-lesCoral" />
            <Text className="text-xs font-bold uppercase tracking-[1.8px] text-lesMuted">
              New session
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close new session"
            onPress={() => router.back()}
            className="flex-row items-center gap-1 rounded-full px-1 py-2"
          >
            <Text className="font-semibold text-lesCoral">Close</Text>
            <Ionicons name="close" size={18} color="#FF5C5C" />
          </Pressable>
        </View>

        <PageHeader
          eyebrow="CHOOSE YOUR WORKFLOW"
          title="What are we looking at?"
          subtitle="Pick the way you want to practice. You can switch workflows any time you start a new session."
        />

        <View className="gap-4">
          <ModeCard
            number="MODE A"
            title="Build the formation"
            detail="Use one video to map a top-down formation and see how your group moves through the space."
            icon="navigate"
            tint="#C8F36A"
            onPress={() => router.push("/create-mode-a")}
          />
          <ModeCard
            number="MODE B"
            title="Compare two takes"
            detail="Bring a reference and your attempt together, then review where the performance drifts."
            icon="git-compare"
            tint="#FF5C5C"
            onPress={() => router.push("/create-mode-b")}
          />
        </View>

        <View className="flex-row items-start gap-3 rounded-2xl bg-lesInk p-4">
          <Ionicons name="sparkles" size={18} color="#C8F36A" />
          <Text className="flex-1 text-xs leading-5 text-lesBackground/75">
            Not sure yet? Mode A is the quickest way to understand spacing. Mode B is best when you have a clip to match.
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}
