import { ScrollView, View, Text } from "react-native";
import PageHeader from "@/components/PageHeader";
import ActionTile from "@/components/ActionTile";
import GroupCard from "@/components/GroupCard";

export default function GroupsScreen() {
  return (
    <ScrollView className="flex-1 bg-lesBackground">
      <View className="p-5 gap-[22px]">
        <PageHeader
          eyebrow="TOGETHER"
          title="Your people, your practice."
          subtitle="Share a take with your crew when you are ready. Analysis stays private until you choose to share."
        />

        <View className="flex-row gap-3">
          <ActionTile title="Create group" icon="add" tint="#FF5C5C" />
          <ActionTile title="Join with code" icon="person-add" tint="#C8F36A" />
        </View>

        <View className="gap-3">
          <Text className="text-lg font-bold text-lesInk">Your groups</Text>
          <GroupCard
            name="Weekend Trend Crew"
            detail="3 dancers · 1 recent session"
          />
          <GroupCard
            name="No groups yet"
            detail="Share an analysis when you are ready."
            isEmpty
          />
        </View>
      </View>
    </ScrollView>
  );
}
