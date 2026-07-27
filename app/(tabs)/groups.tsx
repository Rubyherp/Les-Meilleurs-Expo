import { ScrollView, View, Text, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import PageHeader from "@/components/PageHeader";
import ActionTile from "@/components/ActionTile";
import GroupCard from "@/components/GroupCard";
import { logger } from "@/utils/logger";

export default function GroupsScreen() {
  const handleCreateGroup = () => {
    logger.ui.press("Create group");
    Alert.alert(
      "Coming soon",
      "Group creation isn't available yet. Groups will appear here once the feature is ready.",
    );
  };

  const handleJoinWithCode = () => {
    logger.ui.press("Join with code");
    Alert.alert(
      "Coming soon",
      "Joining groups with a code isn't available yet. Check back when group features launch.",
    );
  };

  const handleViewGroup = () => {
    logger.ui.press("View group: Weekend Trend Crew");
    Alert.alert(
      "Coming soon",
      "Group details aren't available yet. This is a preview of the upcoming group feature.",
    );
  };

  const handleNoGroups = () => {
    logger.ui.press("No groups yet");
    Alert.alert(
      "No groups yet",
      "You haven't joined any groups. Create one or join with a code once group features launch.",
    );
  };

  return (
    <SafeAreaView edges={["top"]} className="flex-1 bg-lesBackground">
      <ScrollView className="flex-1">
        <View className="p-5 gap-[22px]">
          <PageHeader
            eyebrow="TOGETHER"
            title="Your people, your practice."
            subtitle="Share a take with your crew when you are ready. Analysis stays private until you choose to share."
          />

          <View className="flex-row gap-3">
            <ActionTile
              title="Create group"
              icon="add"
              tint="#FF5C5C"
              onPress={handleCreateGroup}
            />
            <ActionTile
              title="Join with code"
              icon="person-add"
              tint="#C8F36A"
              onPress={handleJoinWithCode}
            />
          </View>

          <View className="gap-3">
            <Text className="text-lg font-bold text-lesInk">Your groups</Text>
            <GroupCard
              name="Weekend Trend Crew"
              detail="3 dancers · 1 recent session"
              onPress={handleViewGroup}
            />
            <GroupCard
              name="No groups yet"
              detail="Share an analysis when you are ready."
              isEmpty
              onPress={handleNoGroups}
            />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
