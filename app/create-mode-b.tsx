import { useRef, useState } from "react";
import {
  Pressable,
  ScrollView,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { logger } from "@/utils/logger";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import {
  CameraView,
  useCameraPermissions,
  useMicrophonePermissions,
} from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";
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

export default function CreateModeBScreen() {
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
  const [isLoadingRef, setIsLoadingRef] = useState(false);
  const [isLoadingAttempt, setIsLoadingAttempt] = useState(false);
  const [step, setStep] = useState<Step>("reference");
  const [isCameraVisible, setIsCameraVisible] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const cameraRef = useRef<CameraView>(null);
  const cameraSessionActive = useRef(false);
  const [, requestCameraPermission] = useCameraPermissions();
  const [, requestMicrophonePermission] = useMicrophonePermissions();

  const pickVideo = async (isReference: boolean) => {
    // Prevent duplicate selection while already loading
    if ((isReference && isLoadingRef) || (!isReference && isLoadingAttempt)) return;

    const setLoading = isReference ? setIsLoadingRef : setIsLoadingAttempt;
    setLoading(true);
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) return;
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
    } finally {
      setLoading(false);
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
    logger.ui.press("Analyze my practice (Mode B)");
    const session = store.createSession(title, isGroup, {
      attemptVideoUri,
      referenceVideoUri,
      calibrationCorners,
    });
    router.dismissAll();
    setTimeout(() => {
      store.setPresentedSession(session);
      router.push(`/analysis/${session.id}`);
    }, 100);
  };

  const canContinue = title.trim().length > 0;

  return (
    <SafeAreaView edges={["top", "bottom"]} className="flex-1 bg-lesBackground">
      <ScrollView className="flex-1 bg-lesBackground" contentContainerClassName="pb-8">
        <View className="gap-6 p-5">
          <View className="flex-row items-center justify-between">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go back to mode selection"
              onPress={() => {
                logger.ui.press("Back (Mode B)");
                router.back();
              }}
              className="flex-row items-center gap-1 py-2"
            >
              <Ionicons name="chevron-back" size={20} color="#FF5C5C" />
              <Text className="font-semibold text-lesCoral">Back</Text>
            </Pressable>
            <Text className="text-xs font-bold uppercase tracking-[1.5px] text-lesMuted">
              Mode B
            </Text>
          </View>

          {step === "reference" ? (
            <>
              <PageHeader
                eyebrow="STEP 01 OF 02 · COMPARE TWO TAKES"
                title="Add the reference."
                subtitle="Choose a short social trend clip where the dancer is visible head-to-toe. Ten to sixty seconds works best."
              />
              <View className="gap-3">
                <Text className="font-semibold text-lesInk">What are you practicing?</Text>
                <TextInput
                  className="rounded-2xl border border-lesLine bg-white/70 p-4 text-lesInk"
                  placeholder="e.g. Saturday night trend"
                  placeholderTextColor="#747475"
                  value={title}
                  onChangeText={(text) => {
                    setTitle(text);
                    logger.ui.input("title", "changed");
                  }}
                />
                <View className="flex-row items-center justify-between">
                  <Text className="text-lesInk">This is a group choreography</Text>
                  <Switch
                    value={isGroup}
                    onValueChange={(value) => {
                      setIsGroup(value);
                      logger.ui.input("group choreography", value ? "on" : "off");
                    }}
                    trackColor={{ false: "#DAD6CC", true: "#FF5C5C" }}
                  />
                </View>
              </View>
              <Pressable onPress={() => {
                logger.ui.press("Choose reference video (Mode B)");
                pickVideo(true);
              }}>
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
              {isLoadingRef && <InlineStatus text="Preparing your reference…" icon="sync" />}
              <Pressable
                onPress={() => {
                  logger.ui.press("Add my attempt");
                  setStep("attempt");
                }}
                disabled={!canContinue}
              >
                <PrimaryButton title="Add my attempt" enabled={canContinue} />
              </Pressable>
              <Text className="text-center text-xs text-lesMuted">
                Reference selection is optional for the single-take MVP.
              </Text>
            </>
          ) : (
            <>
              <PageHeader
                eyebrow="STEP 02 OF 02 · YOUR TAKE"
                title="Your turn."
                subtitle="Record with your phone or choose a take from Photos. Keep your full body in frame and use a stable surface."
              />
              <View className="flex-row gap-3">
                <AttemptOption
                  title="Record now"
                  icon="videocam"
                  tint="#FF5C5C"
                  onPress={() => {
                    logger.ui.press("Record now (Mode B)");
                    showCamera();
                  }}
                />
                <AttemptOption
                  title="Choose video"
                  icon="images"
                  tint="#C8F36A"
                  onPress={() => {
                    logger.ui.press("Choose video (Mode B)");
                    pickVideo(false);
                  }}
                />
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
                  <Text className="text-xs text-lesMuted">
                    Set the four visible stage corners before recording. These corners are sent with your take.
                  </Text>
                  <View className="flex-row gap-3">
                    <Pressable
                      className="flex-1 items-center rounded-xl bg-lesCoral p-4"
                      onPress={() => {
                        logger.ui.press(isRecording ? "Stop recording (Mode B)" : "Start recording (Mode B)");
                        if (isRecording) cancelCamera();
                        else recordAttempt();
                      }}
                    >
                      <Text className="font-semibold text-white">{isRecording ? "Stop" : "Record"}</Text>
                    </Pressable>
                    {!isRecording && (
                      <Pressable
                        className="flex-1 items-center rounded-xl border border-white/40 p-4"
                        onPress={() => {
                          logger.ui.press("Cancel camera (Mode B)");
                          cancelCamera();
                        }}
                      >
                        <Text className="font-semibold text-white">Cancel</Text>
                      </Pressable>
                    )}
                  </View>
                </View>
              )}
              {isLoadingAttempt && <InlineStatus text="Preparing your take…" icon="sync" />}
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
    </SafeAreaView>
  );
}
