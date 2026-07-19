import { useEffect, useRef, useState } from "react";
import { PanResponder, StyleSheet, Text, View } from "react-native";
import { NormalizedTopDownPosition } from "../models/Phase4Result";
import {
  CalibrationCorners,
  DEFAULT_CALIBRATION_CORNERS,
} from "../models/Calibration";
import { Colors } from "../theme/colors";

export interface CalibrationPreviewRect {
  width: number;
  height: number;
}

interface Props {
  previewRect: CalibrationPreviewRect;
  initialCorners?: CalibrationCorners;
  onCornersChange?: (corners: CalibrationCorners) => void;
}

const CORNER_LABELS = ["1 · top left", "2 · top right", "3 · bottom right", "4 · bottom left"];

function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

function CornerHandle({
  index,
  point,
  previewRect,
  onMove,
}: {
  index: number;
  point: NormalizedTopDownPosition;
  previewRect: CalibrationPreviewRect;
  onMove: (point: NormalizedTopDownPosition) => void;
}) {
  const pointRef = useRef(point);
  pointRef.current = point;
  const start = useRef(point);
  const responder = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => { start.current = pointRef.current; },
    onPanResponderMove: (_, gesture) => onMove({
      x: clamp(start.current.x + gesture.dx / Math.max(1, previewRect.width)),
      y: clamp(start.current.y + gesture.dy / Math.max(1, previewRect.height)),
    }),
    onPanResponderTerminationRequest: () => false,
  })).current;

  return (
    <View
      {...responder.panHandlers}
      accessibilityLabel={`Drag calibration corner ${CORNER_LABELS[index]}`}
      style={[styles.handleWrap, { left: `${point.x * 100}%`, top: `${point.y * 100}%` }]}
    >
      <View style={styles.handle}><Text style={styles.handleNumber}>{index + 1}</Text></View>
    </View>
  );
}

/** Reusable four-point calibration overlay for a camera/video preview. */
export default function CalibrationOverlay({ previewRect, initialCorners, onCornersChange }: Props) {
  const [corners, setCorners] = useState<CalibrationCorners>(
    initialCorners ?? DEFAULT_CALIBRATION_CORNERS
  );

  useEffect(() => {
    onCornersChange?.(corners);
  }, [corners, onCornersChange]);

  return (
    <View style={[styles.wrapper, { width: previewRect.width, height: previewRect.height }]}>
      <View pointerEvents="none" style={styles.guide} />
      {corners.map((point, index) => (
        <CornerHandle
          key={index}
          index={index}
          point={point}
          previewRect={previewRect}
          onMove={(nextPoint) => setCorners((current) => {
            const next = [...current] as CalibrationCorners;
            next[index] = nextPoint;
            return next;
          })}
        />
      ))}
      <View pointerEvents="none" style={styles.instructionCard}>
        <Text style={styles.instructionTitle}>Set the stage corners</Text>
        <Text style={styles.instructionCopy}>Drag 1 → 2 → 3 → 4 around the visible dance floor.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { position: "relative", overflow: "hidden", backgroundColor: "rgba(23,23,29,0.16)" },
  guide: { ...StyleSheet.absoluteFillObject, borderWidth: 1, borderColor: Colors.lesLime },
  handleWrap: { position: "absolute", width: 48, height: 48, marginLeft: -24, marginTop: -24, alignItems: "center", justifyContent: "center" },
  handle: { width: 28, height: 28, borderRadius: 14, borderWidth: 3, borderColor: Colors.lesBackground, backgroundColor: Colors.lesCoral, alignItems: "center", justifyContent: "center", shadowColor: "#000", shadowOpacity: 0.28, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 4 },
  handleNumber: { color: Colors.lesInk, fontSize: 11, fontWeight: "900" },
  instructionCard: { position: "absolute", left: 12, right: 12, bottom: 12, backgroundColor: "rgba(23,23,29,0.9)", borderRadius: 10, padding: 10 },
  instructionTitle: { color: Colors.lesBackground, fontSize: 12, fontWeight: "800" },
  instructionCopy: { color: "rgba(247,244,238,0.7)", fontSize: 10, lineHeight: 14, marginTop: 2 },
});
