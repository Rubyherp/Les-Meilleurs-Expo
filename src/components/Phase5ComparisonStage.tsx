import { useState } from "react";
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from "react-native";
import {
  NormalizedTopDownPosition,
  Phase4Frame,
  Phase4GridMetadata,
  Phase4Track,
  Phase4TrackId,
} from "../models/Phase4Result";
import { Phase5Match } from "../models/Phase5Result";
import { Colors } from "../theme/colors";
import { getDancerColor } from "./TopDownGrid";

export type ComparisonMode = "overlay" | "side-by-side";

interface Props {
  grid: Phase4GridMetadata;
  referenceFrame?: Phase4Frame;
  attemptFrame?: Phase4Frame;
  matches: Phase5Match[];
  selectedMatch: Phase5Match | null;
  mode: ComparisonMode;
  onSelectMatch: (match: Phase5Match) => void;
  labelForMatch: (match: Phase5Match) => string;
  side?: "reference" | "attempt";
}

function sameId(left: Phase4TrackId, right: Phase4TrackId) {
  return String(left) === String(right);
}

function displayPosition(position: NormalizedTopDownPosition, grid: Phase4GridMetadata) {
  return {
    x: Math.max(0, Math.min(1, position.x)),
    y: Math.max(0, Math.min(1, grid.coordinateOrigin === "bottom_left" ? 1 - position.y : position.y)),
  };
}

function matchForTrack(trackId: Phase4TrackId, side: "reference" | "attempt", matches: Phase5Match[]) {
  return matches.find((match) => sameId(trackId, side === "reference" ? match.referenceTrackId : match.attemptTrackId));
}

function Connector({
  from,
  to,
  color,
  width,
  height,
}: {
  from: NormalizedTopDownPosition;
  to: NormalizedTopDownPosition;
  color: string;
  width: number;
  height: number;
}) {
  const x1 = from.x * width;
  const y1 = from.y * height;
  const x2 = to.x * width;
  const y2 = to.y * height;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  if (length < 1) return null;
  return (
    <View
      pointerEvents="none"
      style={{
        position: "absolute",
        left: x1,
        top: y1 - 1,
        width: length,
        height: 2,
        backgroundColor: color,
        opacity: 0.5,
        transform: [{ rotate: `${angle}deg` }],
      }}
    />
  );
}

function StageMarker({
  track,
  match,
  grid,
  selected,
  ghost,
  label,
  onPress,
}: {
  track: Phase4Track;
  match: Phase5Match | undefined;
  grid: Phase4GridMetadata;
  selected: boolean;
  ghost: boolean;
  label: string;
  onPress: () => void;
}) {
  if (!track.position) return null;
  const position = displayPosition(track.position, grid);
  const color = getDancerColor(match?.referenceTrackId ?? track.id);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}${ghost ? ", reference" : ", attempt"}${selected ? ", selected" : ""}`}
      hitSlop={7}
      onPress={onPress}
      style={[styles.markerButton, { left: `${position.x * 100}%`, top: `${position.y * 100}%` }]}
    >
      <View
        style={[
          styles.marker,
          ghost ? styles.ghostMarker : styles.solidMarker,
          { borderColor: color },
          !ghost && { backgroundColor: color },
          selected && styles.selectedMarker,
        ]}
      >
        <Text style={[styles.markerText, { color: ghost ? color : Colors.lesInk }]}>{String(track.id).slice(-2)}</Text>
      </View>
      {selected && <Text style={[styles.markerLabel, { color }]}>{label}</Text>}
    </Pressable>
  );
}

export default function Phase5ComparisonStage({
  grid,
  referenceFrame,
  attemptFrame,
  matches,
  selectedMatch,
  mode,
  onSelectMatch,
  labelForMatch,
  side,
}: Props) {
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const isOverlay = mode === "overlay";
  const activeSide = side ?? "reference";
  const frame = activeSide === "reference" ? referenceFrame : attemptFrame;
  const tracks = frame?.tracks.filter((track) => track.position) ?? [];
  const hasPositions = isOverlay
    ? (referenceFrame?.tracks.some((track) => track.position) ?? false) ||
      (attemptFrame?.tracks.some((track) => track.position) ?? false)
    : tracks.length > 0;
  const empty = !hasPositions;

  const onLayout = (event: LayoutChangeEvent) => {
    setStageSize({ width: event.nativeEvent.layout.width, height: event.nativeEvent.layout.height });
  };

  const renderTrack = (track: Phase4Track, trackSide: "reference" | "attempt", ghost: boolean) => {
    const match = matchForTrack(track.id, trackSide, matches);
    const selected = !!match && !!selectedMatch &&
      sameId(match.referenceTrackId, selectedMatch.referenceTrackId) &&
      sameId(match.attemptTrackId, selectedMatch.attemptTrackId);
    return (
      <StageMarker
        key={`${trackSide}-${String(track.id)}`}
        track={track}
        match={match}
        grid={grid}
        selected={selected}
        ghost={ghost}
        label={match ? labelForMatch(match) : `Dancer ${track.id}`}
        onPress={() => match && onSelectMatch(match)}
      />
    );
  };

  const selectedPair = selectedMatch
    ? {
        reference: referenceFrame?.tracks.find((track) => sameId(track.id, selectedMatch.referenceTrackId))?.position,
        attempt: attemptFrame?.tracks.find((track) => sameId(track.id, selectedMatch.attemptTrackId))?.position,
      }
    : null;
  const selectedReference = selectedPair?.reference ? displayPosition(selectedPair.reference, grid) : null;
  const selectedAttempt = selectedPair?.attempt ? displayPosition(selectedPair.attempt, grid) : null;

  return (
    <View style={[styles.wrapper, mode === "side-by-side" && styles.sideWrapper]}>
      <View style={styles.stageTitleRow}>
        <Text style={styles.stageTitle}>{isOverlay ? "Reference + attempt" : activeSide === "reference" ? "Reference" : "Your attempt"}</Text>
        <View style={styles.stageLegend}>
          {!isOverlay && <View style={[styles.legendSwatch, activeSide === "reference" ? styles.ghostLegend : styles.solidLegend]} />}
          <Text style={styles.stageLegendText}>{isOverlay ? "ghost / solid" : activeSide === "reference" ? "ghost" : "solid"}</Text>
        </View>
      </View>
      <View style={[styles.stageShell, { aspectRatio: grid.aspectRatio }]}>
        <View onLayout={onLayout} style={styles.stage}>
          {Array.from({ length: Math.max(0, grid.columns - 1) }).map((_, index) => (
            <View key={`column-${index}`} pointerEvents="none" style={[styles.gridLine, styles.verticalLine, { left: `${((index + 1) / grid.columns) * 100}%` }]} />
          ))}
          {Array.from({ length: Math.max(0, grid.rows - 1) }).map((_, index) => (
            <View key={`row-${index}`} pointerEvents="none" style={[styles.gridLine, styles.horizontalLine, { top: `${((index + 1) / grid.rows) * 100}%` }]} />
          ))}
          {isOverlay && selectedReference && selectedAttempt && stageSize.width > 0 && (
            <Connector from={selectedReference} to={selectedAttempt} color={Colors.lesCoral} width={stageSize.width} height={stageSize.height} />
          )}
          {isOverlay ? (
            <>
              {(referenceFrame?.tracks ?? []).map((track) => renderTrack(track, "reference", true))}
              {(attemptFrame?.tracks ?? []).map((track) => renderTrack(track, "attempt", false))}
            </>
          ) : tracks.map((track) => renderTrack(track, activeSide, activeSide === "reference"))}
          {empty && (
            <View style={styles.emptyOverlay}>
              <Text style={styles.emptyTitle}>No aligned positions</Text>
              <Text style={styles.emptyCopy}>This moment has no usable top-down points.</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: 7 },
  sideWrapper: { flex: 1 },
  stageTitleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stageTitle: { color: Colors.lesInk, fontSize: 12, fontWeight: "900" },
  stageLegend: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendSwatch: { width: 9, height: 9, borderRadius: 5 },
  ghostLegend: { borderWidth: 1.5, borderColor: Colors.lesCoral },
  solidLegend: { backgroundColor: Colors.lesCoral },
  stageLegendText: { color: Colors.lesMuted, fontSize: 10, fontWeight: "700" },
  stageShell: { position: "relative" },
  stage: { flex: 1, overflow: "hidden", borderRadius: 14, backgroundColor: "#24242D", borderColor: "#41414A", borderWidth: 1 },
  gridLine: { position: "absolute", backgroundColor: "rgba(247,244,238,0.13)" },
  verticalLine: { top: 0, bottom: 0, width: 1 },
  horizontalLine: { left: 0, right: 0, height: 1 },
  markerButton: { position: "absolute", width: 42, height: 42, marginLeft: -21, marginTop: -21, alignItems: "center", justifyContent: "center", zIndex: 2 },
  marker: { width: 23, height: 23, borderRadius: 12, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  ghostMarker: { backgroundColor: "rgba(247,244,238,0.08)", borderStyle: "dashed" },
  solidMarker: { borderColor: Colors.lesInk },
  selectedMarker: { width: 31, height: 31, borderRadius: 16, borderWidth: 3, borderColor: Colors.lesBackground },
  markerText: { fontSize: 8, fontWeight: "900" },
  markerLabel: { position: "absolute", top: 34, backgroundColor: Colors.lesInk, borderRadius: 4, paddingHorizontal: 5, paddingVertical: 2, fontSize: 9, fontWeight: "800" },
  emptyOverlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: 20, backgroundColor: "rgba(36,36,45,0.84)" },
  emptyTitle: { color: Colors.lesBackground, fontSize: 13, fontWeight: "800", textAlign: "center" },
  emptyCopy: { color: "rgba(247,244,238,0.62)", fontSize: 10, textAlign: "center", marginTop: 4 },
});
