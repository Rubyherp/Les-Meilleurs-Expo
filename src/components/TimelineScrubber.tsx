import { useCallback, useMemo, useState } from "react";
import { LayoutChangeEvent, PanResponder, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Colors } from "../theme/colors";

interface Props {
  currentFrameIndex: number;
  frameCount: number;
  currentTimeSeconds: number;
  durationSeconds: number;
  isPlaying: boolean;
  onTogglePlaying: () => void;
  onSeekFrame: (frameIndex: number) => void;
}

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.round(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

export default function TimelineScrubber({
  currentFrameIndex,
  frameCount,
  currentTimeSeconds,
  durationSeconds,
  isPlaying,
  onTogglePlaying,
  onSeekFrame,
}: Props) {
  const [trackWidth, setTrackWidth] = useState(1);
  const progress = frameCount <= 1 ? 0 : currentFrameIndex / (frameCount - 1);

  const seekFromX = useCallback((x: number) => {
    if (frameCount <= 1) return;
    const next = Math.round(Math.max(0, Math.min(trackWidth, x)) / trackWidth * (frameCount - 1));
    onSeekFrame(next);
  }, [frameCount, onSeekFrame, trackWidth]);

  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (event) => seekFromX(event.nativeEvent.locationX),
    onPanResponderMove: (event) => seekFromX(event.nativeEvent.locationX),
  }), [seekFromX]);

  const onTrackLayout = (event: LayoutChangeEvent) => setTrackWidth(Math.max(1, event.nativeEvent.layout.width));

  return (
    <View style={styles.container}>
      <View style={styles.topRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={isPlaying ? "Pause floor read" : "Play floor read"}
          onPress={onTogglePlaying}
          style={({ pressed }) => [styles.playButton, pressed && styles.pressed]}
        >
          <Ionicons name={isPlaying ? "pause" : "play"} size={16} color={Colors.lesInk} />
        </Pressable>
        <View style={styles.timeLabels}>
          <Text style={styles.time}>{formatTime(currentTimeSeconds)}</Text>
          <Text style={styles.duration}>{formatTime(durationSeconds)}</Text>
        </View>
        <Text style={styles.frameLabel}>{frameCount ? `Frame ${currentFrameIndex + 1}` : "Waiting for frames"}</Text>
      </View>
      <View
        {...responder.panHandlers}
        onLayout={onTrackLayout}
        accessibilityRole="adjustable"
        accessibilityLabel="Analysis timeline"
        style={styles.trackTouchArea}
      >
        <Pressable onPress={(event) => seekFromX(event.nativeEvent.locationX)} style={styles.track}>
          <View style={[styles.progress, { width: `${progress * 100}%` }]} />
          <View style={[styles.thumb, { left: `${progress * 100}%` }]} />
        </Pressable>
      </View>
      <View style={styles.hintRow}>
        <Text style={styles.hint}>Drag to inspect spacing</Text>
        <Text style={styles.hint}>Observed / predicted</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 10 },
  topRow: { flexDirection: "row", alignItems: "center" },
  playButton: { width: 34, height: 34, borderRadius: 17, backgroundColor: Colors.lesCoral, alignItems: "center", justifyContent: "center" },
  pressed: { transform: [{ scale: 0.94 }] },
  timeLabels: { flexDirection: "row", alignItems: "baseline", marginLeft: 10, gap: 4 },
  time: { color: Colors.lesInk, fontSize: 13, fontWeight: "800", fontVariant: ["tabular-nums"] },
  duration: { color: Colors.lesMuted, fontSize: 11, fontVariant: ["tabular-nums"] },
  frameLabel: { color: Colors.lesMuted, fontSize: 11, fontWeight: "700", marginLeft: "auto" },
  trackTouchArea: { height: 30, justifyContent: "center" },
  track: { height: 6, borderRadius: 4, backgroundColor: Colors.lesLine, justifyContent: "center" },
  progress: { height: 6, borderRadius: 4, backgroundColor: Colors.lesCoral },
  thumb: { position: "absolute", width: 16, height: 16, borderRadius: 8, marginLeft: -8, backgroundColor: Colors.lesInk, borderWidth: 3, borderColor: Colors.lesBackground },
  hintRow: { flexDirection: "row", justifyContent: "space-between" },
  hint: { color: Colors.lesMuted, fontSize: 10 },
});
