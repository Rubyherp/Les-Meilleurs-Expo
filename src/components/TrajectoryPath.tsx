import { StyleSheet, View } from "react-native";
import {
  Phase4Frame,
  Phase4TrackId,
  Phase4CoordinateOrigin,
  NormalizedTopDownPosition,
} from "../models/Phase4Result";
import { Colors } from "../theme/colors";

export type TrailMode = "all" | "selected" | "none";

interface Props {
  frames: Phase4Frame[];
  stageWidth: number;
  stageHeight: number;
  colorForTrack: (trackId: Phase4TrackId) => string;
  mode: TrailMode;
  selectedTrackId?: Phase4TrackId | null;
  coordinateOrigin?: Phase4CoordinateOrigin;
}

function sameTrack(left: Phase4TrackId, right: Phase4TrackId | null | undefined) {
  return right !== null && right !== undefined && String(left) === String(right);
}

function displayPosition(
  position: NormalizedTopDownPosition,
  origin: Phase4CoordinateOrigin
) {
  return {
    x: Math.max(0, Math.min(1, position.x)),
    y: Math.max(0, Math.min(1, origin === "bottom_left" ? 1 - position.y : position.y)),
  };
}

function Line({
  from,
  to,
  color,
  width,
  opacity,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
  width: number;
  opacity: number;
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.sqrt(dx * dx + dy * dy);
  if (length < 1) return null;
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;

  return (
    <View
      pointerEvents="none"
      style={{
        position: "absolute",
        left: from.x,
        top: from.y - width / 2,
        width: length,
        height: width,
        borderRadius: width,
        backgroundColor: color,
        opacity,
        transform: [{ rotate: `${angle}deg` }],
      }}
    />
  );
}

function DashedLine({
  from,
  to,
  color,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.sqrt(dx * dx + dy * dy);
  const dashCount = Math.max(1, Math.ceil(length / 10));
  const pieces = [];

  for (let index = 0; index < dashCount; index += 2) {
    const start = index / dashCount;
    const end = Math.min(1, (index + 1) / dashCount);
    pieces.push(
      <Line
        key={`${index}-${start}`}
        from={{ x: from.x + dx * start, y: from.y + dy * start }}
        to={{ x: from.x + dx * end, y: from.y + dy * end }}
        color={color}
        width={2}
        opacity={0.62}
      />
    );
  }
  return <>{pieces}</>;
}

/** Renders short native Views instead of requiring an SVG/canvas dependency. */
export default function TrajectoryPath({
  frames,
  stageWidth,
  stageHeight,
  colorForTrack,
  mode,
  selectedTrackId,
  coordinateOrigin = "top_left",
}: Props) {
  if (mode === "none" || stageWidth <= 0 || stageHeight <= 0) return null;

  const pointsByTrack = new Map<
    string,
    { position: { x: number; y: number }; predicted: boolean }[]
  >();
  const ids = new Map<string, Phase4TrackId>();

  frames.forEach((frame) => {
    frame.tracks.forEach((track) => {
      if (!track.position || (mode === "selected" && !sameTrack(track.id, selectedTrackId))) {
        return;
      }
      const key = String(track.id);
      ids.set(key, track.id);
      const position = displayPosition(track.position, coordinateOrigin);
      const points = pointsByTrack.get(key) ?? [];
      points.push({
        position: { x: position.x * stageWidth, y: position.y * stageHeight },
        predicted: track.source !== "observed",
      });
      pointsByTrack.set(key, points);
    });
  });

  return (
    <View pointerEvents="none" style={{ ...StyleSheet.absoluteFillObject }}>
      {Array.from(pointsByTrack.entries()).map(([key, points]) => {
        const color = colorForTrack(ids.get(key)!);
        return points.slice(1).map((point, index) => {
          const previous = points[index];
          return point.predicted || previous.predicted ? (
            <DashedLine
              key={`${key}-${index}`}
              from={previous.position}
              to={point.position}
              color={color}
            />
          ) : (
            <Line
              key={`${key}-${index}`}
              from={previous.position}
              to={point.position}
              color={color}
              width={3}
              opacity={0.42}
            />
          );
        });
      })}
    </View>
  );
}

export const TRAIL_PREDICTED_COLOR = Colors.lesLime;
