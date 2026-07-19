import { useMemo, useState } from "react";
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from "react-native";
import {
  Phase4GridMetadata,
  Phase4Frame,
  Phase4TrackId,
  Phase4Track,
} from "../models/Phase4Result";
import TrajectoryPath, { TrailMode } from "./TrajectoryPath";
import { Colors } from "../theme/colors";

export const DANCER_COLORS = [
  "#FF5C5C", "#C8F36A", "#62D5C8", "#FFB454", "#9C8CFF", "#F28EDB",
  "#63A7FF", "#E8E16B", "#FF8A65", "#72E0A5", "#B99CFF", "#F5B7D2",
  "#4DD0E1", "#FFD166", "#A8E063", "#FF7B9C", "#7CA8FF", "#E0A5FF",
  "#FF9F68", "#84DCC6", "#F6D365", "#B8C0FF", "#FF7F50", "#94D2BD",
] as const;

interface Props {
  grid: Phase4GridMetadata;
  frames: Phase4Frame[];
  currentFrameIndex: number;
  trailMode?: TrailMode;
  selectedTrackId?: Phase4TrackId | null;
  onSelectTrack?: (trackId: Phase4TrackId) => void;
  labelForTrack?: (trackId: Phase4TrackId) => string;
}

function displayY(track: Phase4Track, grid: Phase4GridMetadata) {
  const y = track.position?.y ?? 0;
  return grid.coordinateOrigin === "bottom_left" ? 1 - y : y;
}

export function getDancerColor(trackId: Phase4TrackId) {
  const value = String(trackId);
  let hash = 17;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return DANCER_COLORS[Math.abs(hash) % DANCER_COLORS.length];
}

function labelAt(labels: string[], index: number, count: number) {
  if (labels[index]) return labels[index];
  return `${Math.round((index / Math.max(1, count - 1)) * 10) / 10}`;
}

export default function TopDownGrid({
  grid,
  frames,
  currentFrameIndex,
  trailMode = "all",
  selectedTrackId = null,
  onSelectTrack,
  labelForTrack = (id) => `Dancer ${id}`,
}: Props) {
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const currentFrame = frames[currentFrameIndex];
  const currentTracks = useMemo(
    () => currentFrame?.tracks.filter((track) => track.position) ?? [],
    [currentFrame]
  );
  const hasCalibration = grid.calibration
    ? grid.calibration.status === "calibrated"
    : grid.calibrated;

  const onStageLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setStageSize({ width, height });
  };

  return (
    <View style={styles.card}>
      <View style={styles.stageHeading}>
        <View>
          <Text style={styles.eyebrow}>LIVE FLOOR READ</Text>
          <Text style={styles.title}>Top-down formation</Text>
        </View>
        <View style={styles.framePill}>
          <Text style={styles.framePillText}>
            {frames.length ? `${currentFrameIndex + 1} / ${frames.length}` : "—"}
          </Text>
        </View>
      </View>

      <View style={[styles.stageShell, { aspectRatio: grid.aspectRatio }]}>
        <View onLayout={onStageLayout} style={styles.stage}>
          {Array.from({ length: Math.max(0, grid.columns - 1) }).map((_, index) => (
            <View
              key={`column-${index}`}
              pointerEvents="none"
              style={[styles.gridLine, styles.verticalLine, { left: `${((index + 1) / grid.columns) * 100}%` }]}
            />
          ))}
          {Array.from({ length: Math.max(0, grid.rows - 1) }).map((_, index) => (
            <View
              key={`row-${index}`}
              pointerEvents="none"
              style={[styles.gridLine, styles.horizontalLine, { top: `${((index + 1) / grid.rows) * 100}%` }]}
            />
          ))}
          <View pointerEvents="none" style={styles.centerLine} />

          <TrajectoryPath
            frames={frames}
            stageWidth={stageSize.width}
            stageHeight={stageSize.height}
            colorForTrack={getDancerColor}
            mode={trailMode}
            selectedTrackId={selectedTrackId}
            coordinateOrigin={grid.coordinateOrigin}
          />

          {currentTracks.map((track) => {
            const isSelected = selectedTrackId !== null && String(selectedTrackId) === String(track.id);
            const color = getDancerColor(track.id);
            const y = displayY(track, grid);
            return (
              <Pressable
                key={String(track.id)}
                accessibilityRole="button"
                accessibilityLabel={`${labelForTrack(track.id)}${isSelected ? ", selected" : ""}`}
                hitSlop={8}
                onPress={() => onSelectTrack?.(track.id)}
                style={[
                  styles.dancerButton,
                  { left: `${(track.position?.x ?? 0) * 100}%`, top: `${y * 100}%` },
                ]}
              >
                <View style={[styles.dancerDot, { backgroundColor: color }, isSelected && styles.selectedDot]}>
                  <Text style={styles.dancerNumber}>{String(track.id).slice(-2)}</Text>
                </View>
                {isSelected && <Text style={[styles.dancerLabel, { color }]}>{labelForTrack(track.id)}</Text>}
              </Pressable>
            );
          })}

          {!frames.length && (
            <View style={styles.emptyOverlay}>
              <Text style={styles.emptyTitle}>No movement data yet</Text>
              <Text style={styles.emptyCopy}>The floor read will appear when this analysis is ready.</Text>
            </View>
          )}
          {!!frames.length && !currentTracks.length && hasCalibration && (
            <View style={styles.emptyOverlay}>
              <Text style={styles.emptyTitle}>No dancers in this frame</Text>
              <Text style={styles.emptyCopy}>Try another moment on the timeline.</Text>
            </View>
          )}
          {!!frames.length && !hasCalibration && (
            <View style={styles.calibrationOverlay}>
              <View style={styles.calibrationIcon}><Text style={styles.calibrationIconText}>+</Text></View>
              <Text style={styles.calibrationTitle}>Stage not calibrated</Text>
              <Text style={styles.calibrationCopy}>Add the four stage corners to place dancers on the floor.</Text>
            </View>
          )}
        </View>

        <View pointerEvents="none" style={styles.yLabels}>
          {Array.from({ length: grid.rows }).map((_, index) => (
            <Text key={`y-label-${index}`} style={styles.axisLabel}>
              {labelAt(grid.yLabels, index, grid.rows)}
            </Text>
          ))}
        </View>
        <View pointerEvents="none" style={styles.xLabels}>
          {Array.from({ length: grid.columns }).map((_, index) => (
            <Text key={`x-label-${index}`} style={[styles.axisLabel, styles.xAxisLabel]}>
              {labelAt(grid.xLabels, index, grid.columns)}
            </Text>
          ))}
        </View>
      </View>

      <View style={styles.legend}>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: Colors.lesCoral }]} /><Text style={styles.legendText}>Observed</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, styles.predictedDot]} /><Text style={styles.legendText}>Predicted</Text></View>
        <Text style={styles.unitText}>{grid.unit ? `Grid: ${grid.unit}` : "Normalized stage coordinates"}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: Colors.lesInk, borderRadius: 26, padding: 16, gap: 14 },
  stageHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  eyebrow: { color: Colors.lesCoral, fontSize: 10, fontWeight: "800", letterSpacing: 1.6 },
  title: { color: Colors.lesBackground, fontSize: 21, fontWeight: "800", marginTop: 4 },
  framePill: { backgroundColor: "#303039", borderRadius: 99, paddingHorizontal: 10, paddingVertical: 6 },
  framePillText: { color: Colors.lesLime, fontSize: 11, fontWeight: "800" },
  stageShell: { marginLeft: 12, marginRight: 12, position: "relative" },
  stage: { flex: 1, overflow: "hidden", backgroundColor: "#24242D", borderWidth: 1, borderColor: "#41414A", borderRadius: 14 },
  gridLine: { position: "absolute", backgroundColor: "rgba(247,244,238,0.13)" },
  verticalLine: { top: 0, bottom: 0, width: 1 },
  horizontalLine: { left: 0, right: 0, height: 1 },
  centerLine: { position: "absolute", top: 0, bottom: 0, left: "50%", width: 1, backgroundColor: "rgba(255,92,92,0.28)" },
  dancerButton: { position: "absolute", width: 44, height: 44, marginLeft: -22, marginTop: -22, alignItems: "center", justifyContent: "center" },
  dancerDot: { width: 25, height: 25, borderRadius: 13, borderWidth: 2, borderColor: Colors.lesInk, alignItems: "center", justifyContent: "center", shadowColor: "#000", shadowOpacity: 0.25, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  selectedDot: { width: 32, height: 32, borderRadius: 16, borderColor: Colors.lesBackground, borderWidth: 3 },
  dancerNumber: { color: Colors.lesInk, fontSize: 9, fontWeight: "900" },
  dancerLabel: { position: "absolute", top: 36, backgroundColor: Colors.lesInk, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, fontSize: 9, fontWeight: "800" },
  emptyOverlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: 28, backgroundColor: "rgba(36,36,45,0.86)" },
  emptyTitle: { color: Colors.lesBackground, fontSize: 15, fontWeight: "800", textAlign: "center" },
  emptyCopy: { color: Colors.lesMuted, fontSize: 12, lineHeight: 17, textAlign: "center", marginTop: 5 },
  calibrationOverlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: 22, backgroundColor: "rgba(23,23,29,0.8)" },
  calibrationIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: Colors.lesCoral, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  calibrationIconText: { color: Colors.lesInk, fontSize: 22, fontWeight: "300", lineHeight: 24 },
  calibrationTitle: { color: Colors.lesBackground, fontWeight: "800", fontSize: 15 },
  calibrationCopy: { color: Colors.lesBackground, opacity: 0.72, fontSize: 12, textAlign: "center", lineHeight: 17, marginTop: 5, maxWidth: 210 },
  yLabels: { position: "absolute", left: -12, top: 0, bottom: 0, justifyContent: "space-between" },
  xLabels: { position: "absolute", left: 0, right: 0, bottom: -19, flexDirection: "row", justifyContent: "space-between" },
  axisLabel: { color: "rgba(247,244,238,0.55)", fontSize: 8, minWidth: 12 },
  xAxisLabel: { textAlign: "center" },
  legend: { flexDirection: "row", alignItems: "center", gap: 13, flexWrap: "wrap" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  predictedDot: { backgroundColor: Colors.lesLime, opacity: 0.65 },
  legendText: { color: "rgba(247,244,238,0.65)", fontSize: 10, fontWeight: "700" },
  unitText: { color: "rgba(247,244,238,0.42)", fontSize: 10, marginLeft: "auto" },
});
