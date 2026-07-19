import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { GroupParticipant } from "../models/GroupParticipant";
import { Phase4Frame, Phase4TrackId } from "../models/Phase4Result";
import {
  Phase5Deviation,
  Phase5Match,
  Phase5Result,
} from "../models/Phase5Result";
import TimelineScrubber from "./TimelineScrubber";
import Phase5ComparisonStage, { ComparisonMode } from "./Phase5ComparisonStage";
import { Colors } from "../theme/colors";
import { formatScore } from "../utils/format";

interface Props {
  result: Phase5Result;
  participants?: GroupParticipant[];
  durationSeconds?: number;
}

type DeviationSeverity = "steady" | "watch" | "drift";

function matchKey(match: Phase5Match) {
  return `${String(match.referenceTrackId)}::${String(match.attemptTrackId)}`;
}

function severityFor(deviation: Phase5Deviation | undefined): DeviationSeverity {
  if (!deviation) return "steady";
  if (deviation.maxDistance >= 0.28 || deviation.meanDistance >= 0.16) return "drift";
  if (deviation.maxDistance >= 0.14 || deviation.meanDistance >= 0.07) return "watch";
  return "steady";
}

function severityColor(severity: DeviationSeverity) {
  if (severity === "drift") return Colors.lesCoral;
  if (severity === "watch") return "#D4952A";
  return "#6EAD45";
}

function distancePercent(value: number) {
  return `${Math.round(Math.max(0, value) * 100)}%`;
}

function distinctTrackIds(frames: Phase4Frame[]) {
  const ids = new Map<string, Phase4TrackId>();
  frames.forEach((frame) => frame.tracks.forEach((track) => ids.set(String(track.id), track.id)));
  return ids;
}

function deriveMatches(result: Phase5Result): Phase5Match[] {
  if (result.matches.length) return result.matches;
  const referenceIds = distinctTrackIds(result.reference.frames);
  const attemptIds = distinctTrackIds(result.attempt.frames);
  return Array.from(referenceIds.entries())
    .filter(([key]) => attemptIds.has(key))
    .map(([key, referenceTrackId]) => ({ referenceTrackId, attemptTrackId: attemptIds.get(key)! }));
}

function frameIndexFor(result: Phase5Result, timelineIndex: number, side: "reference" | "attempt", timelineCount: number) {
  const pair = result.alignment?.framePairs[timelineIndex];
  if (pair) return side === "reference" ? pair.referenceFrameIndex : pair.attemptFrameIndex;
  const count = side === "reference" ? result.reference.frames.length : result.attempt.frames.length;
  if (count <= 1 || timelineCount <= 1) return 0;
  return Math.round((timelineIndex / (timelineCount - 1)) * (count - 1));
}

export default function Phase5ComparisonView({ result, participants = [], durationSeconds }: Props) {
  const [mode, setMode] = useState<ComparisonMode>("overlay");
  const [timelineIndex, setTimelineIndex] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const matches = useMemo(() => deriveMatches(result), [result]);
  const framePairs = result.alignment?.framePairs ?? [];
  const timelineCount = Math.max(framePairs.length, result.reference.frames.length, result.attempt.frames.length);
  const frameRate = Math.max(1, result.reference.frameRate ?? result.attempt.frameRate ?? 10);
  const referenceIndex = frameIndexFor(result, timelineIndex, "reference", timelineCount);
  const attemptIndex = frameIndexFor(result, timelineIndex, "attempt", timelineCount);
  const referenceFrame = result.reference.frames[referenceIndex];
  const attemptFrame = result.attempt.frames[attemptIndex];
  const selectedMatch = matches.find((match) => matchKey(match) === selectedKey) ?? null;
  const labels = useMemo(() => new Map(participants.map((participant) => [participant.id, participant.displayName])), [participants]);
  const deviationsByMatch = useMemo(() => new Map(result.deviations.map((deviation) => [
    matchKey({ referenceTrackId: deviation.referenceTrackId, attemptTrackId: deviation.attemptTrackId }),
    deviation,
  ])), [result.deviations]);
  const selectedDeviation = selectedMatch ? deviationsByMatch.get(matchKey(selectedMatch)) : undefined;
  const worstOffenders = useMemo(() => [...result.deviations]
    .sort((left, right) => right.maxDistance - left.maxDistance || right.meanDistance - left.meanDistance)
    .slice(0, 3), [result.deviations]);

  const duration = durationSeconds ?? Math.max(
    0.5,
    result.reference.frames[result.reference.frames.length - 1]?.timestampSeconds ??
      result.attempt.frames[result.attempt.frames.length - 1]?.timestampSeconds ?? 0
  );

  useEffect(() => {
    setTimelineIndex(0);
    setSelectedKey(null);
    setIsPlaying(false);
  }, [result]);

  useEffect(() => {
    if (!isPlaying || timelineCount <= 1) return;
    const timer = setInterval(() => {
      setTimelineIndex((current) => {
        if (current >= timelineCount - 1) {
          setIsPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1000 / frameRate);
    return () => clearInterval(timer);
  }, [frameRate, isPlaying, timelineCount]);

  const labelForMatch = (match: Phase5Match) => {
    const participantName = labels.get(String(match.attemptTrackId)) ?? labels.get(String(match.referenceTrackId));
    return participantName ?? `Dancer ${matches.indexOf(match) + 1}`;
  };
  const currentReferenceIndex = referenceIndex;
  const currentAttemptIndex = attemptIndex;
  const currentTime = referenceFrame?.timestampSeconds ?? attemptFrame?.timestampSeconds ?? 0;
  const currentPoint = selectedDeviation?.perFrame.find((point) =>
    point.referenceFrameIndex === currentReferenceIndex && point.attemptFrameIndex === currentAttemptIndex
  );

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>PHASE 5 · COMPARISON</Text>
          <Text style={styles.heading}>Find the shared beat.</Text>
          <Text style={styles.subtitle}>Reference ghost, your take, one room to read.</Text>
        </View>
        <View style={styles.scoreBadge}>
          <Text style={styles.score}>{formatScore(result.overallScore)}</Text>
          <Text style={styles.scoreLabel}>MATCH</Text>
        </View>
      </View>

      <View style={styles.modeCard}>
        <View style={styles.modeHeader}>
          <Text style={styles.modeTitle}>Compare formation</Text>
          <Text style={styles.modeHint}>{matches.length} matched {matches.length === 1 ? "dancer" : "dancers"}</Text>
        </View>
        <View style={styles.segmentedControl}>
          {(["overlay", "side-by-side"] as ComparisonMode[]).map((option) => (
            <Pressable
              key={option}
              accessibilityRole="button"
              accessibilityState={{ selected: mode === option }}
              onPress={() => setMode(option)}
              style={[styles.segment, mode === option && styles.segmentSelected]}
            >
              <Text style={[styles.segmentText, mode === option && styles.segmentTextSelected]}>
                {option === "overlay" ? "Overlay" : "Side by side"}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {mode === "overlay" ? (
        <Phase5ComparisonStage
          grid={result.reference.grid}
          referenceFrame={referenceFrame}
          attemptFrame={attemptFrame}
          matches={matches}
          selectedMatch={selectedMatch}
          mode={mode}
          onSelectMatch={(match) => setSelectedKey(matchKey(match))}
          labelForMatch={labelForMatch}
        />
      ) : (
        <View style={styles.sideBySide}>
          <Phase5ComparisonStage
            grid={result.reference.grid}
            referenceFrame={referenceFrame}
            attemptFrame={attemptFrame}
            matches={matches}
            selectedMatch={selectedMatch}
            mode={mode}
            side="reference"
            onSelectMatch={(match) => setSelectedKey(matchKey(match))}
            labelForMatch={labelForMatch}
          />
          <Phase5ComparisonStage
            grid={result.attempt.grid}
            referenceFrame={referenceFrame}
            attemptFrame={attemptFrame}
            matches={matches}
            selectedMatch={selectedMatch}
            mode={mode}
            side="attempt"
            onSelectMatch={(match) => setSelectedKey(matchKey(match))}
            labelForMatch={labelForMatch}
          />
        </View>
      )}

      <View style={styles.timelineCard}>
        <TimelineScrubber
          currentFrameIndex={timelineIndex}
          frameCount={timelineCount}
          currentTimeSeconds={currentTime}
          durationSeconds={duration}
          isPlaying={isPlaying}
          onTogglePlaying={() => {
            if (!timelineCount) return;
            if (timelineIndex >= timelineCount - 1) setTimelineIndex(0);
            setIsPlaying((playing) => !playing);
          }}
          onSeekFrame={(index) => {
            setTimelineIndex(index);
            setIsPlaying(false);
          }}
        />
        <View style={styles.timelineNote}>
          <View style={styles.legendRow}><View style={styles.ghostDot} /><Text style={styles.legendText}>Reference</Text></View>
          <View style={styles.legendRow}><View style={styles.solidDot} /><Text style={styles.legendText}>Your attempt</Text></View>
          {result.alignment && <Text style={styles.alignmentCost}>Alignment {result.alignment.cost.toFixed(2)}</Text>}
        </View>
      </View>

      <View style={styles.dancerSection}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Inspect a dancer</Text>
          {selectedMatch && <Pressable onPress={() => setSelectedKey(null)}><Text style={styles.clear}>Clear</Text></Pressable>}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.dancerRail}>
          {matches.map((match, index) => {
            const isSelected = matchKey(match) === selectedKey;
            const deviation = deviationsByMatch.get(matchKey(match));
            const severity = severityFor(deviation);
            return (
              <Pressable
                key={matchKey(match)}
                accessibilityRole="button"
                accessibilityState={{ selected: isSelected }}
                onPress={() => setSelectedKey(isSelected ? null : matchKey(match))}
                style={[styles.dancerChip, isSelected && styles.dancerChipSelected]}
              >
                <View style={[styles.chipDot, { backgroundColor: severityColor(severity) }]} />
                <Text style={[styles.chipText, isSelected && styles.chipTextSelected]}>{labelForMatch(match) || `Dancer ${index + 1}`}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {selectedMatch && (
        <View style={styles.deviationCard}>
          <View style={styles.deviationHeader}>
            <View>
              <Text style={styles.deviationEyebrow}>SELECTED DANCER</Text>
              <Text style={styles.deviationTitle}>{labelForMatch(selectedMatch)}</Text>
            </View>
            <View style={[styles.severityPill, { backgroundColor: severityColor(severityFor(selectedDeviation)) }]}>
              <Text style={styles.severityText}>{severityFor(selectedDeviation).toUpperCase()}</Text>
            </View>
          </View>
          <View style={styles.metricRow}>
            <View style={styles.metric}><Text style={styles.metricValue}>{selectedDeviation ? distancePercent(selectedDeviation.meanDistance) : "—"}</Text><Text style={styles.metricLabel}>mean drift</Text></View>
            <View style={styles.metric}><Text style={styles.metricValue}>{selectedDeviation ? distancePercent(selectedDeviation.maxDistance) : "—"}</Text><Text style={styles.metricLabel}>worst drift</Text></View>
            <View style={styles.metric}><Text style={styles.metricValue}>{currentPoint ? distancePercent(currentPoint.distance) : "—"}</Text><Text style={styles.metricLabel}>this frame</Text></View>
          </View>
        </View>
      )}

      <View style={styles.offendersSection}>
        <View style={styles.sectionHeader}>
          <View><Text style={styles.sectionTitle}>Worth a second look</Text><Text style={styles.sectionSubtitle}>Largest normalized deviations</Text></View>
          <Text style={styles.offenderCount}>{worstOffenders.length} shown</Text>
        </View>
        {worstOffenders.length ? worstOffenders.map((deviation) => {
          const match = { referenceTrackId: deviation.referenceTrackId, attemptTrackId: deviation.attemptTrackId };
          const severity = severityFor(deviation);
          const selected = matchKey(match) === selectedKey;
          return (
            <Pressable
              key={matchKey(match)}
              onPress={() => setSelectedKey(matchKey(match))}
              style={[styles.offenderRow, selected && styles.offenderRowSelected]}
            >
              <View style={[styles.offenderDot, { backgroundColor: severityColor(severity) }]} />
              <Text style={styles.offenderName}>{labelForMatch(match)}</Text>
              <Text style={styles.offenderDistance}>{distancePercent(deviation.maxDistance)}</Text>
              <Text style={[styles.offenderSeverity, { color: severityColor(severity) }]}>{severity}</Text>
            </Pressable>
          );
        }) : (
          <Text style={styles.emptyOffenders}>No deviation details were returned for this comparison.</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 14 },
  headerRow: { flexDirection: "row", alignItems: "flex-end" },
  headerCopy: { flex: 1, gap: 3 },
  eyebrow: { color: Colors.lesCoral, fontSize: 10, fontWeight: "900", letterSpacing: 1.8 },
  heading: { color: Colors.lesInk, fontSize: 28, fontWeight: "900", letterSpacing: -0.7 },
  subtitle: { color: Colors.lesMuted, fontSize: 13, lineHeight: 18 },
  scoreBadge: { width: 64, height: 64, borderRadius: 32, backgroundColor: Colors.lesInk, alignItems: "center", justifyContent: "center", transform: [{ rotate: "-5deg" }] },
  score: { color: Colors.lesCoral, fontSize: 24, fontWeight: "900", lineHeight: 25 },
  scoreLabel: { color: Colors.lesBackground, fontSize: 8, fontWeight: "900", letterSpacing: 1 },
  modeCard: { backgroundColor: "#EEEAE1", borderRadius: 18, padding: 12, gap: 9 },
  modeHeader: { flexDirection: "row", alignItems: "center" },
  modeTitle: { color: Colors.lesInk, fontSize: 12, fontWeight: "900" },
  modeHint: { color: Colors.lesMuted, fontSize: 10, marginLeft: "auto" },
  segmentedControl: { flexDirection: "row", backgroundColor: Colors.lesBackground, borderRadius: 10, padding: 3, gap: 3 },
  segment: { flex: 1, minHeight: 34, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  segmentSelected: { backgroundColor: Colors.lesInk },
  segmentText: { color: Colors.lesMuted, fontSize: 11, fontWeight: "800" },
  segmentTextSelected: { color: Colors.lesBackground },
  sideBySide: { flexDirection: "row", gap: 9 },
  timelineCard: { backgroundColor: "#EEEAE1", borderRadius: 20, padding: 15, gap: 9 },
  timelineNote: { flexDirection: "row", alignItems: "center", gap: 13 },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  ghostDot: { width: 9, height: 9, borderRadius: 5, borderWidth: 1.5, borderStyle: "dashed", borderColor: Colors.lesCoral },
  solidDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: Colors.lesCoral },
  legendText: { color: Colors.lesMuted, fontSize: 10, fontWeight: "700" },
  alignmentCost: { color: Colors.lesMuted, fontSize: 10, marginLeft: "auto" },
  dancerSection: { gap: 8 },
  sectionHeader: { flexDirection: "row", alignItems: "center" },
  sectionTitle: { color: Colors.lesInk, fontSize: 15, fontWeight: "900" },
  sectionSubtitle: { color: Colors.lesMuted, fontSize: 11, marginTop: 2 },
  clear: { color: Colors.lesCoral, fontSize: 11, fontWeight: "900", marginLeft: "auto" },
  dancerRail: { gap: 7, paddingVertical: 3 },
  dancerChip: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#EEEAE1", borderRadius: 99, paddingHorizontal: 10, minHeight: 34, maxWidth: 130 },
  dancerChipSelected: { backgroundColor: Colors.lesInk },
  chipDot: { width: 8, height: 8, borderRadius: 4 },
  chipText: { color: Colors.lesInk, fontSize: 10, fontWeight: "800" },
  chipTextSelected: { color: Colors.lesBackground },
  deviationCard: { backgroundColor: Colors.lesInk, borderRadius: 20, padding: 15, gap: 14 },
  deviationHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  deviationEyebrow: { color: Colors.lesCoral, fontSize: 9, fontWeight: "900", letterSpacing: 1.4 },
  deviationTitle: { color: Colors.lesBackground, fontSize: 19, fontWeight: "900", marginTop: 3 },
  severityPill: { borderRadius: 99, paddingHorizontal: 8, paddingVertical: 5 },
  severityText: { color: Colors.lesInk, fontSize: 9, fontWeight: "900", letterSpacing: 0.8 },
  metricRow: { flexDirection: "row", gap: 8 },
  metric: { flex: 1, backgroundColor: "#2A2A33", borderRadius: 11, padding: 10 },
  metricValue: { color: Colors.lesLime, fontSize: 18, fontWeight: "900" },
  metricLabel: { color: "rgba(247,244,238,0.55)", fontSize: 9, marginTop: 2 },
  offendersSection: { gap: 8 },
  offenderCount: { color: Colors.lesMuted, fontSize: 10, marginLeft: "auto" },
  offenderRow: { flexDirection: "row", alignItems: "center", backgroundColor: "#EEEAE1", borderRadius: 12, paddingHorizontal: 12, minHeight: 43, gap: 8 },
  offenderRowSelected: { borderWidth: 1, borderColor: Colors.lesCoral },
  offenderDot: { width: 8, height: 8, borderRadius: 4 },
  offenderName: { color: Colors.lesInk, fontSize: 12, fontWeight: "800", flex: 1 },
  offenderDistance: { color: Colors.lesInk, fontSize: 12, fontWeight: "900" },
  offenderSeverity: { fontSize: 9, fontWeight: "900", width: 45, textAlign: "right" },
  emptyOffenders: { color: Colors.lesMuted, fontSize: 12, paddingVertical: 8 },
});
