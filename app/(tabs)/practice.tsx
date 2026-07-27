import { ScrollView, View, Text, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { logger } from "@/utils/logger";
import { useAppStore } from "@/store/useAppStore";
import PageHeader from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import SessionCard from "@/components/SessionCard";
import EmptyStateCard from "@/components/EmptyStateCard";

export default function PracticeScreen() {
  const store = useAppStore();
  const router = useRouter();

  const handleCreate = () => {
    logger.ui.press("Start a new session");
    store.setShowingCreate(true);
    router.push("/create-session");
  };

  const handleSessionPress = (session: any) => {
    logger.ui.press(`Open session: ${session.title}`);
    store.setPresentedSession(session);
    router.push(`/analysis/${session.id}`);
  };

  return (
    <SafeAreaView edges={["top"]} className="flex-1 bg-lesBackground">
      <ScrollView className="flex-1">
        <View className="p-5 gap-6">
          <PageHeader
            eyebrow="LES MEILLEURS"
            title="Ready for one more take?"
            subtitle="Bring a trend, record your version, and get clear next steps."
          />

          <View className="flex-row gap-2.5">
            <MetricCard value={String(store.sessions.length)} label="sessions" />
            <MetricCard value="1" label="new streak" tint="#FF5C5C" />
            <MetricCard value="—" label="latest gain" />
          </View>

          <Pressable
            onPress={handleCreate}
            className="bg-lesCoral rounded-[26px] p-5 flex-row items-center"
          >
            <View className="flex-1 gap-1">
              <Text className="text-lg font-bold text-lesInk">
                Start a new session
              </Text>
              <Text className="text-sm text-lesInk/70">
                Turn a trend into your next practice win.
              </Text>
            </View>
            <View className="w-[46px] h-[46px] bg-lesInk rounded-full items-center justify-center">
              <Ionicons name="open-outline" size={22} color="#F7F4EE" />
            </View>
          </Pressable>

          {store.sessions.length === 0 ? (
            <EmptyStateCard onAction={handleCreate} />
          ) : (
            <View className="gap-3">
              <Text className="text-lg font-bold text-lesInk">
                Recent practice
              </Text>
              {store.sessions.map((session) => (
                <Pressable
                  key={session.id}
                  onPress={() => handleSessionPress(session)}
                >
                  <SessionCard session={session} />
                </Pressable>
              ))}
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
