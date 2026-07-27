import { ScrollView, View, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import PageHeader from "@/components/PageHeader";
import SettingsRow from "@/components/SettingsRow";

export default function ProfileScreen() {
  return (
    <SafeAreaView edges={["top"]} className="flex-1 bg-lesBackground">
      <ScrollView className="flex-1">
        <View className="p-5 gap-[22px]">
          <PageHeader
            eyebrow="YOUR SPACE"
            title="Make every take count."
            subtitle="A supportive practice studio for social dance trends. Your movement is yours."
          />

          <View className="p-5 bg-white/60 border border-lesLine rounded-3xl">
            <Text className="text-2xl font-bold text-lesInk mb-3">
              Les Meilleurs
            </Text>
            <Text className="text-base text-lesMuted">
              Sharing is always explicit. Your videos and movement data stay
              private until you choose otherwise.
            </Text>
          </View>

          <View className="px-4 bg-white/60 border border-lesLine rounded-3xl">
            <SettingsRow
              icon="camera"
              title="Camera access"
              detail="Needed when you record a take"
            />
            <View className="h-px bg-lesLine ml-[54px]" />
            <SettingsRow
              icon="images"
              title="Photo library"
              detail="Choose reference and attempt videos"
            />
            <View className="h-px bg-lesLine ml-[54px]" />
            <SettingsRow
              icon="lock-closed"
              title="Privacy first"
              detail="Sharing is always explicit"
            />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
