import "../global.css";
import { useRef } from "react";
import { Stack, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { logger } from "@/utils/logger";

function NavigationLogger() {
  const segments = useSegments();
  const previous = useRef<string>("app");

  const current = segments.join("/") || "app";
  if (current !== previous.current) {
    logger.ui.navigate(previous.current, current);
    previous.current = current;
  }
  return null;
}

export default function RootLayout() {
  logger.system("App mounted");
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <NavigationLogger />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="create-session"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="create-mode-a"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="create-mode-b"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="analysis/[id]"
          options={{ presentation: "modal" }}
        />
      </Stack>
    </SafeAreaProvider>
  );
}
