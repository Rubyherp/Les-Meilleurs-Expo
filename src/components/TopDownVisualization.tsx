import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { GroupParticipant } from "../models/GroupParticipant";
import { Phase4Result, Phase4TrackId } from "../models/Phase4Result";
import TopDownGrid from "./TopDownGrid";
import TimelineScrubber from "./TimelineScrubber";
import { TrailMode } from "./TrajectoryPath";
import { Colors } from "../theme/colors";

interface Props {
  result: Phase4Result;
  participants?: GroupParticipant[];
  durationSeconds?: number;
  seekTimestampSeconds?: number | null;
}

const TRAIL_OPTIONS: { value: TrailMode; label: string }[] = [
  { value: "all", label: "All trails" },
  { value: "selected", label: "Selected" },
  { value: "none", label: "None" },
];

export default function TopDownVisualization({ result, participants = [], durationSeconds, seekTimestampSeconds }: Props) {
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [selectedTrackId, setSelectedTrackId] = useState<Phase4TrackId | null>(null);
  const [trailMode, setTrailMode] = useState<TrailMode>("all");
  const [isPlaying, setIsPlaying] = useState(false);

  const labels = useMemo(() => new Map(participants.map((participant) => [participant.id, participant.displayName])), [participants]);
  const trackIds = useMemo(() => {
    const ids = new Map<string, Phase4TrackId>();
    result.frames.forEach((frame) => frame.tracks.forEach((track) => ids.set(String(track.id), track.id)));
    return Array.from(ids.values());
  }, [result.frames]);
  const frame = result.frames[currentFrameIndex];
  const frameRate = Math.max(1, result.frameRate ?? 10);
  const inferredDuration = result.frames.length ? result.frames[result.frames.length - 1].timestampSeconds : 0;
  const duration = durationSeconds ?? Math.max(0.5, inferredDuration);

  useEffect(() => {
    if (!isPlaying || result.frames.length <= 1) return;
    const timer = setInterval(() => {
      setCurrentFrameIndex((current) => {
        if (current >= result.frames.length - 1) {
          setIsPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1000 / frameRate);
    return () => clearInterval(timer);
  }, [frameRate, isPlaying, result.frames.length]);

  useEffect(() => {
    setCurrentFrameIndex(0);
    setIsPlaying(false);
  }, [result]);

  useEffect(() => {
    if (seekTimestampSeconds == null || !result.frames.length) return;
    let nearest = 0;
    result.frames.forEach((item, index) => {
      if (Math.abs(item.timestampSeconds - seekTimestampSeconds) < Math.abs(result.frames[nearest].timestampSeconds - seekTimestampSeconds)) nearest = index;
    });
    setCurrentFrameIndex(nearest);
    setIsPlaying(false);
  }, [seekTimestampSeconds, result.frames]);

  const labelForTrack = (trackId: Phase4TrackId) => labels.get(String(trackId)) ?? `Dancer ${trackId}`;
  const selectedTrack = frame?.tracks.find((track) => String(track.id) === String(selectedTrackId));
  const selectedSource = selectedTrack?.source === "predicted" ? "Predicted position" : "Observed position";

  return (
    <View style={styles.container}>
      <View style={styles.introRow}>
        <View style={styles.introCopy}>
          <Text style={styles.eyebrow}>PHASE 4 · GROUP VIEW</Text>
          <Text style={styles.heading}>See the room move.</Text>
          <Text style={styles.subtitle}>Replay spacing, entrances, and the moments that drift.</Text>
        </View>
        <View style={styles.countBadge}>
          <Text style={styles.countNumber}>{trackIds.length}</Text>
          <Text style={styles.countLabel}>dancers</Text>
        </View>
      </View>

      <TopDownGrid
        grid={result.grid}
        frames={result.frames}
        currentFrameIndex={currentFrameIndex}
        trailMode={trailMode}
        selectedTrackId={selectedTrackId}
        onSelectTrack={(trackId) => setSelectedTrackId((current) => String(current) === String(trackId) ? null : trackId)}
        labelForTrack={labelForTrack}
      />

      <View style={styles.controlsCard}>
        <TimelineScrubber
          currentFrameIndex={currentFrameIndex}
          frameCount={result.frames.length}
          currentTimeSeconds={frame?.timestampSeconds ?? 0}
          durationSeconds={duration}
          isPlaying={isPlaying}
          onTogglePlaying={() => {
            if (!result.frames.length) return;
            if (currentFrameIndex >= result.frames.length - 1) setCurrentFrameIndex(0);
            setIsPlaying((playing) => !playing);
          }}
          onSeekFrame={(frameIndex) => {
            setCurrentFrameIndex(frameIndex);
            setIsPlaying(false);
          }}
        />
        <View style={styles.controlDivider} />
        <View style={styles.trailHeader}>
          <Text style={styles.controlLabel}>Trajectory trails</Text>
          <Text style={styles.controlHint}>{selectedTrackId !== null ? labelForTrack(selectedTrackId) : "Group overview"}</Text>
        </View>
        <View style={styles.segmentedControl}>
          {TRAIL_OPTIONS.map((option) => (
            <Pressable
              key={option.value}
              accessibilityRole="button"
              accessibilityState={{ selected: trailMode === option.value }}
              onPress={() => setTrailMode(option.value)}
              style={[styles.segment, trailMode === option.value && styles.segmentSelected]}
            >
              <Text style={[styles.segmentText, trailMode === option.value && styles.segmentTextSelected]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        {selectedTrackId !== null && (
          <View style={styles.selectedInfo}>
            <View style={styles.selectedDot} />
            <Text style={styles.selectedText}>{labelForTrack(selectedTrackId)} · {selectedSource}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Clear selected dancer" onPress={() => setSelectedTrackId(null)}>
              <Text style={styles.clearText}>Clear</Text>
            </Pressable>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 14 },
  introRow: { flexDirection: "row", alignItems: "flex-end" },
  introCopy: { flex: 1, gap: 3 },
  eyebrow: { color: Colors.lesCoral, fontSize: 10, fontWeight: "900", letterSpacing: 1.8 },
  heading: { color: Colors.lesInk, fontSize: 28, fontWeight: "900", letterSpacing: -0.7 },
  subtitle: { color: Colors.lesMuted, fontSize: 13, lineHeight: 18, paddingRight: 8 },
  countBadge: { width: 58, height: 58, borderRadius: 29, backgroundColor: Colors.lesLime, alignItems: "center", justifyContent: "center", transform: [{ rotate: "5deg" }] },
  countNumber: { color: Colors.lesInk, fontSize: 20, fontWeight: "900", lineHeight: 20 },
  countLabel: { color: Colors.lesInk, fontSize: 9, fontWeight: "800" },
  controlsCard: { backgroundColor: "#EEEAE1", borderRadius: 20, padding: 15, gap: 10 },
  controlDivider: { height: 1, backgroundColor: Colors.lesLine },
  trailHeader: { flexDirection: "row", alignItems: "center" },
  controlLabel: { color: Colors.lesInk, fontSize: 12, fontWeight: "900" },
  controlHint: { color: Colors.lesMuted, fontSize: 11, marginLeft: "auto" },
  segmentedControl: { flexDirection: "row", backgroundColor: Colors.lesBackground, borderRadius: 10, padding: 3, gap: 3 },
  segment: { flex: 1, minHeight: 34, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  segmentSelected: { backgroundColor: Colors.lesInk },
  segmentText: { color: Colors.lesMuted, fontSize: 11, fontWeight: "800" },
  segmentTextSelected: { color: Colors.lesBackground },
  selectedInfo: { flexDirection: "row", alignItems: "center", gap: 7 },
  selectedDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.lesCoral },
  selectedText: { color: Colors.lesInk, fontSize: 11, fontWeight: "700", flex: 1 },
  clearText: { color: Colors.lesCoral, fontSize: 11, fontWeight: "900" },
});
