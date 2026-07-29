import { useRef, useState } from "react";
import { CameraView, useCameraPermissions, useMicrophonePermissions } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Pressable, ScrollView, Switch, Text, TextInput, View } from "react-native";
import { logger } from "@/utils/logger";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAppStore } from "@/store/useAppStore";
import PageHeader from "@/components/PageHeader";
import MediaImportCard from "@/components/MediaImportCard";
import AttemptOption from "@/components/AttemptOption";
import PrimaryButton from "@/components/PrimaryButton";
import InlineStatus from "@/components/InlineStatus";
import TipCard from "@/components/TipCard";
import CalibrationOverlay from "@/components/CalibrationOverlay";
import DancerCountSelector from "@/components/DancerCountSelector";
import {
  CalibrationCorners,
  DEFAULT_CALIBRATION_CORNERS,
} from "@/models/Calibration";

export default function CreateModeAScreen() {
  const store = useAppStore();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [isGroup, setIsGroup] = useState(false);
  const [expectedDancerCount, setExpectedDancerCount] = useState(3);
  const [videoUri, setVideoUri] = useState<string | undefined>();
  const [videoSource, setVideoSource] = useState<"recorded" | "library" | undefined>();
  const [calibrationCorners, setCalibrationCorners] = useState<CalibrationCorners>(
    DEFAULT_CALIBRATION_CORNERS
  );
  const [previewRect, setPreviewRect] = useState({ width: 0, height: 0 });
  const [isCameraVisible, setIsCameraVisible] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const cameraRef = useRef<CameraView>(null);
  const cameraSessionActive = useRef(false);
  const [, requestCameraPermission] = useCameraPermissions();
  const [, requestMicrophonePermission] = useMicrophonePermissions();

  const pickVideo = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
    });
    if (!result.canceled && result.assets.length > 0) {
      setVideoUri(result.assets[0].uri);
      setVideoSource("library");
      setCalibrationCorners(DEFAULT_CALIBRATION_CORNERS);
    }
  };

  const showCamera = async () => {
    try {
      const [cameraPermission, microphonePermission] = await Promise.all([
        requestCameraPermission(),
        requestMicrophonePermission(),
      ]);
      if (!cameraPermission.granted || !microphonePermission.granted) return;
      cameraSessionActive.current = true;
      setIsCameraVisible(true);
    } catch {
      cameraSessionActive.current = false;
    }
  };

  const recordVideo = async () => {
    if (!cameraRef.current || isRecording) return;
    setIsRecording(true);
    try {
      const recording = await cameraRef.current.recordAsync({ maxDuration: 60 });
      const uri = recording?.uri;
      if (!uri) throw new Error("The camera did not return a video URI.");
      if (cameraSessionActive.current) {
        setVideoUri(uri);
        setVideoSource("recorded");
        cameraSessionActive.current = false;
        setIsCameraVisible(false);
      }
    } catch {
      // Stopping or closing the camera can reject the recording promise.
    } finally {
      setIsRecording(false);
    }
  };

  const cancelCamera = () => {
    cameraSessionActive.current = false;
    cameraRef.current?.stopRecording();
    setIsRecording(false);
    setIsCameraVisible(false);
  };

  const handleAnalyze = () => {
    logger.ui.press("Build my formation (analyze)");
    const session = store.createSession(title, isGroup, {
      attemptVideoUri: videoUri,
      calibrationCorners,
    }, expectedDancerCount);
    router.dismissAll();
    setTimeout(() => {
      store.setPresentedSession(session);
      router.push(`/analysis/${session.id}`);
    }, 100);
  };

  const canAnalyze = title.trim().length > 0 && Boolean(videoUri);

  return (
    <SafeAreaView edges={["top", "bottom"]} className="flex-1 bg-lesBackground">
      <ScrollView className="flex-1 bg-lesBackground" contentContainerClassName="pb-8">
        <View className="gap-6 p-5">
          <View className="flex-row items-center justify-between">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go back to mode selection"
              onPress={() => {
                logger.ui.press("Back (Mode A)");
                router.back();
              }}
              className="flex-row items-center gap-1 py-2"
            >
              <Ionicons name="chevron-back" size={20} color="#FF5C5C" />
              <Text className="font-semibold text-lesCoral">Back</Text>
            </Pressable>
            <Text className="text-xs font-bold uppercase tracking-[1.5px] text-lesMuted">
              Mode A
            </Text>
          </View>

          <PageHeader
            eyebrow="SINGLE VIDEO → FORMATION"
            title="Build the formation."
            subtitle="Choose a video with the full group in frame. We will turn the movement into a top-down view of the space."
          />

          <View className="gap-3">
            <Text className="font-semibold text-lesInk">Name this practice</Text>
            <TextInput
              className="rounded-2xl border border-lesLine bg-white/70 p-4 text-lesInk"
              placeholder="e.g. Saturday night formation"
              placeholderTextColor="#747475"
              value={title}
              onChangeText={(text) => {
                setTitle(text);
                logger.ui.input("title", "changed");
              }}
            />
            <View className="flex-row items-center justify-between rounded-2xl border border-lesLine bg-white/45 px-4 py-3">
              <View className="flex-1 gap-0.5">
                <Text className="text-lesInk">Group choreography (2+ dancers)</Text>
                <Text className="text-xs text-lesMuted">
                  Leave off for solo timing and observation coaching.
                </Text>
              </View>
              <Switch
                value={isGroup}
                onValueChange={(value) => {
                  setIsGroup(value);
                  logger.ui.input("group choreography", value ? "on" : "off");
                }}
                trackColor={{ false: "#DAD6CC", true: "#FF5C5C" }}
                thumbColor="#F7F4EE"
              />
            </View>
            {isGroup && (
              <DancerCountSelector
                value={expectedDancerCount}
                onChange={setExpectedDancerCount}
              />
            )}
          </View>

          <View className="gap-3">
            <View className="flex-row items-end justify-between">
              <Text className="font-semibold text-lesInk">Add your video</Text>
              {videoSource && (
                <Text className="text-xs font-semibold uppercase tracking-[1px] text-lesCoral">
                  {videoSource === "recorded" ? "Recorded" : "From library"}
                </Text>
              )}
            </View>
            <View className="flex-row gap-3">
              <AttemptOption
                title="Record now"
                icon="videocam"
                tint="#FF5C5C"
                onPress={() => {
                  logger.ui.press("Record now (Mode A)");
                  showCamera();
                }}
              />
              <AttemptOption
                title="Choose video"
                icon="images"
                tint="#C8F36A"
                onPress={() => {
                  logger.ui.press("Choose video (Mode A)");
                  pickVideo();
                }}
              />
            </View>
          </View>

          {isCameraVisible && (
            <View className="gap-3 overflow-hidden rounded-2xl bg-lesInk p-3">
              <View
                className="h-80 w-full overflow-hidden rounded-xl"
                onLayout={(event) => {
                  const { width, height } = event.nativeEvent.layout;
                  setPreviewRect({ width, height });
                }}
              >
                <CameraView ref={cameraRef} className="flex-1" mode="video" />
                {previewRect.width > 0 && previewRect.height > 0 && (
                  <View className="absolute inset-0">
                    <CalibrationOverlay
                      previewRect={previewRect}
                      initialCorners={calibrationCorners}
                      onCornersChange={setCalibrationCorners}
                    />
                  </View>
                )}
              </View>
              <Text className="text-xs leading-4 text-lesMuted">
                Before you record, place the four handles around the visible dance floor. This helps us read the formation.
              </Text>
              <View className="flex-row gap-3">
                <Pressable
                  className="flex-1 items-center rounded-xl bg-lesCoral p-4"
                  onPress={() => {
                    logger.ui.press(isRecording ? "Stop recording (Mode A)" : "Start recording (Mode A)");
                    if (isRecording) cancelCamera();
                    else recordVideo();
                  }}
                >
                  <Text className="font-semibold text-white">{isRecording ? "Stop" : "Record"}</Text>
                </Pressable>
                {!isRecording && (
                  <Pressable
                    className="flex-1 items-center rounded-xl border border-white/40 p-4"
                    onPress={() => {
                      logger.ui.press("Cancel camera (Mode A)");
                      cancelCamera();
                    }}
                  >
                    <Text className="font-semibold text-white">Cancel</Text>
                  </Pressable>
                )}
              </View>
            </View>
          )}

          {videoSource === "library" && (
            <InlineStatus
              text="Library video: using the default stage corners because there is no preview to calibrate."
              icon="information-circle"
            />
          )}
          {videoUri ? (
            <InlineStatus
              text="Video ready to map."
              icon="checkmark-circle"
              tint="#C8F36A"
            />
          ) : (
            <TipCard
              title="For a clearer map"
              detail="Keep the camera steady, show the whole group, and include the edges of the dance floor."
            />
          )}

          <PrimaryButton
            title="Build my formation"
            enabled={canAnalyze}
            onPress={handleAnalyze}
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
