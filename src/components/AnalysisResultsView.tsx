import { useState } from "react";
import { ScrollView, View, Text, Pressable, Share } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import PageHeader from "./PageHeader";
import PositiveNote from "./PositiveNote";
import SuggestionCard from "./SuggestionCard";
import ComparisonCard from "./ComparisonCard";
import GroupSyncCard from "./GroupSyncCard";
import TopDownVisualization from "./TopDownVisualization";
import Phase5ComparisonView from "./Phase5ComparisonView";
import { DanceSession } from "../models/DanceSession";
import { AnalysisResult } from "../models/AnalysisResult";
import { GroupParticipant } from "../models/GroupParticipant";
import { formatScore } from "../utils/format";

interface Props {
  session: DanceSession;
  result: AnalysisResult;
  participants: GroupParticipant[];
  onPracticeAgain: () => void;
}

export default function AnalysisResultsView({
  session,
  result,
  participants,
  onPracticeAgain,
}: Props) {
  const [selectedTimestamp, setSelectedTimestamp] = useState<number | null>(null);

  const share = async () => {
    await Share.share({
      message: `My ${session.title} practice notes from Les Meilleurs`,
    });
  };

  return (
    <ScrollView className="flex-1 bg-lesBackground">
      <View className="p-5 gap-[22px]">
        <PageHeader
          eyebrow="PRACTICE NOTES"
          title="A better take starts here."
          subtitle="Use the notes to choose one thing to sharpen, then take another shot."
        />

        <View className="p-5 bg-lesInk rounded-[26px] gap-3">
          <View className="flex-row justify-between items-start">
            <View className="flex-1 gap-1">
              <Text className="text-lg font-bold text-lesBackground">
                {session.title}
              </Text>
              <Text className="text-xs text-lesMuted">
                Estimate based on visible timing and movement
              </Text>
            </View>
            <Text className="text-[34px] font-bold text-lesCoral">
              {result.phase4 && !result.comparison ? "—" : formatScore(result.overallScore)}
            </Text>
          </View>
          <Text className="text-base text-lesMuted">
            {result.phase4 && !result.comparison
              ? "Frame-level movement data is ready. Quality scoring will arrive in a later phase."
              : "Your timing is close. Use this as a practice signal, not a judgment of your style."}
          </Text>
        </View>

        {participants.length > 0 && <GroupSyncCard count={participants.length} />}

        {result.comparison && (
          <Phase5ComparisonView
            result={result.comparison}
            participants={participants}
            durationSeconds={session.duration}
          />
        )}

        {result.phase4 && (
          <TopDownVisualization
            result={result.phase4}
            participants={participants}
            durationSeconds={session.duration}
          />
        )}

        <View className="gap-3">
          <Text className="text-lg font-bold text-lesInk">What's working</Text>
          <PositiveNote text="Strong opening position" />
          <PositiveNote text="Good consistency through the first phrase" />
        </View>

        <View className="gap-3">
          <Text className="text-lg font-bold text-lesInk">Try next</Text>
          {result.issues.map((issue) => (
            <SuggestionCard
              key={issue.id}
              issue={issue}
              onReplay={() => setSelectedTimestamp(issue.timestamp)}
            />
          ))}
        </View>

        <ComparisonCard
          referenceSource={require("../../assets/videos/reference.mov")}
          attemptSource={require("../../assets/videos/user-upload.mov")}
          selectedTimestamp={selectedTimestamp}
        />

        <View className="flex-row gap-3">
          <Pressable
            onPress={onPracticeAgain}
            className="flex-1 bg-lesCoral rounded-lg py-3 items-center"
            style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
          >
            <View className="flex-row items-center gap-2">
              <Ionicons name="refresh" size={18} color="#F7F4EE" />
              <Text className="font-semibold text-lesBackground">Practice again</Text>
            </View>
          </Pressable>
          <Pressable
            onPress={share}
            className="w-[50px] h-[44px] border border-lesInk rounded-lg items-center justify-center"
            style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.98 : 1 }] })}
          >
            <Ionicons name="share-outline" size={22} color="#17171D" />
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}
