import { useRef, useState } from "react";
import {
  ScrollView,
  View,
  Text,
  TextInput,
  Pressable,
  Switch,
} from "react-native";
import { useRouter } from "expo-router";
import {
  CameraView,
  useCameraPermissions,
  useMicrophonePermissions,
} from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { useAppStore } from "@/store/useAppStore";
import PageHeader from "@/components/PageHeader";
import MediaImportCard from "@/components/MediaImportCard";
import AttemptOption from "@/components/AttemptOption";
import PrimaryButton from "@/components/PrimaryButton";
import InlineStatus from "@/components/InlineStatus";
import TipCard from "@/components/TipCard";
import CalibrationOverlay from "@/components/CalibrationOverlay";
import {
  CalibrationCorners,
  DEFAULT_CALIBRATION_CORNERS,
} from "@/models/Calibration";

type Step = "reference" | "attempt";

export default function CreateSessionScreen() {
  const store = useAppStore();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [isGroup, setIsGroup] = useState(false);
  const [referenceReady, setReferenceReady] = useState(false);
  const [referenceVideoUri, setReferenceVideoUri] = useState<string | undefined>();
  const [attemptReady, setAttemptReady] = useState(false);
  const [attemptVideoUri, setAttemptVideoUri] = useState<string | undefined>();
  const [attemptSource, setAttemptSource] = useState<"recorded" | "library" | undefined>();
  const [calibrationCorners, setCalibrationCorners] = useState<CalibrationCorners>(
    DEFAULT_CALIBRATION_CORNERS
  );
  const [previewRect, setPreviewRect] = useState({ width: 0, height: 0 });
  const [isLoadingRef] = useState(false);
  const [isLoadingAttempt] = useState(false);
  const [step, setStep] = useState<Step>("reference");
  const [isCameraVisible, setIsCameraVisible] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const cameraRef = useRef<CameraView>(null);
  const cameraSessionActive = useRef(false);
  const [, requestCameraPermission] = useCameraPermissions();
  const [, requestMicrophonePermission] = useMicrophonePermissions();

  const pickVideo = async (isReference: boolean) => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
    });
    if (!result.canceled && result.assets.length > 0) {
      const uri = result.assets[0].uri;
      if (isReference) {
        setReferenceVideoUri(uri);
        setReferenceReady(true);
      } else {
        setAttemptVideoUri(uri);
        setAttemptSource("library");
        setCalibrationCorners(DEFAULT_CALIBRATION_CORNERS);
        setAttemptReady(true);
      }
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

  const recordAttempt = async () => {
    if (!cameraRef.current || isRecording) return;
    setIsRecording(true);
    try {
      const recording = await cameraRef.current.recordAsync({ maxDuration: 60 });
      const uri = recording?.uri;
      if (!uri) throw new Error("The camera did not return a video URI.");
      if (cameraSessionActive.current) {
        setAttemptVideoUri(uri);
        setAttemptSource("recorded");
        setAttemptReady(true);
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
    const session = store.createSession(title, isGroup, {
      attemptVideoUri,
      referenceVideoUri,
      calibrationCorners,
    });
    router.back();
    setTimeout(() => {
      store.setPresentedSession(session);
      router.push(`/analysis/${session.id}`);
    }, 100);
  };

  const canContinue = title.trim().length > 0;

  return (
    <ScrollView className="flex-1 bg-lesBackground">
      <View className="p-5 gap-6">
        <View className="flex-row justify-between items-center">
          <Text className="text-lg font-bold text-lesInk">
            New practice session
          </Text>
          <Pressable onPress={() => router.back()}>
            <Text className="text-lesCoral font-semibold">Close</Text>
          </Pressable>
        </View>

        {step === "reference" ? (
          <>
            <PageHeader
              eyebrow="STEP 01 OF 02"
              title="Add the reference."
              subtitle="Choose a short social trend clip where the dancer is visible head-to-toe. Ten to sixty seconds works best."
            />
            <View className="gap-3">
              <Text className="font-semibold text-lesInk">
                What are you practicing?
              </Text>
              <TextInput
                className="p-4 bg-white/70 border border-lesLine rounded-2xl text-lesInk"
                placeholder="e.g. Saturday night trend"
                placeholderTextColor="#747475"
                value={title}
                onChangeText={setTitle}
              />
              <View className="flex-row items-center justify-between">
                <Text className="text-lesInk">This is a group choreography</Text>
                <Switch
                  value={isGroup}
                  onValueChange={setIsGroup}
                  trackColor={{ false: "#DAD6CC", true: "#FF5C5C" }}
                />
              </View>
            </View>
            <Pressable onPress={() => pickVideo(true)}>
              <MediaImportCard
                title={referenceReady ? "Reference ready" : "Choose from Photos"}
                detail={
                  referenceReady
                    ? "Your reference is ready to compare."
                    : "Upload a trend clip from your library."
                }
                icon={referenceReady ? "checkmark" : "images"}
                tint={referenceReady ? "#C8F36A" : "#FF5C5C"}
              />
            </Pressable>
            {isLoadingRef && (
              <InlineStatus text="Preparing your reference…" icon="sync" />
            )}
            <Pressable
              onPress={() => setStep("attempt")}
              disabled={!canContinue}
            >
              <PrimaryButton title="Add my attempt" enabled={canContinue} />
            </Pressable>
            <Text className="text-xs text-lesMuted text-center">
              Reference selection is optional for the single-take MVP.
            </Text>
          </>
        ) : (
          <>
            <PageHeader
              eyebrow="STEP 02 OF 02"
              title="Your turn."
              subtitle="Record with your phone or choose a take from Photos. Keep your full body in frame and use a stable surface."
            />
            <View className="flex-row gap-3">
              <AttemptOption
                title="Record now"
                icon="videocam"
                tint="#FF5C5C"
                onPress={showCamera}
              />
              <AttemptOption
                title="Choose video"
                icon="images"
                tint="#C8F36A"
                onPress={() => pickVideo(false)}
              />
            </View>
            {isCameraVisible && (
              <View className="gap-3 rounded-2xl overflow-hidden bg-lesInk p-3">
                <View
                  className="h-80 w-full rounded-xl overflow-hidden"
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
                <Text className="text-xs text-lesMuted">
                  Set the four visible stage corners before recording. These corners are sent with your take.
                </Text>
                <View className="flex-row gap-3">
                  <Pressable
                    className="flex-1 rounded-xl bg-lesCoral p-4 items-center"
                    onPress={isRecording ? cancelCamera : recordAttempt}
                  >
                    <Text className="font-semibold text-white">
                      {isRecording ? "Stop" : "Record"}
                    </Text>
                  </Pressable>
                  {!isRecording && (
                    <Pressable
                      className="flex-1 rounded-xl border border-white/40 p-4 items-center"
                      onPress={cancelCamera}
                    >
                      <Text className="font-semibold text-white">Cancel</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            )}
            {isLoadingAttempt && (
              <InlineStatus text="Preparing your take…" icon="sync" />
            )}
            {attemptSource === "library" && (
              <InlineStatus
                text="Library video: using the default stage corners because there is no preview to calibrate."
                icon="information-circle"
              />
            )}
            {attemptReady ? (
              <InlineStatus
                text="Your take is ready to analyze."
                icon="checkmark-circle"
                tint="#C8F36A"
              />
            ) : (
              <TipCard
                title="Camera check"
                detail="If the front view hides a move, capture a second take from a 45° angle. We will flag sections that cannot be read reliably."
              />
            )}
            <Pressable onPress={handleAnalyze} disabled={!attemptReady}>
              <PrimaryButton title="Analyze my practice" enabled={attemptReady} />
            </Pressable>
          </>
        )}
      </View>
    </ScrollView>
  );
}
