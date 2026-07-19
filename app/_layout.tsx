import "../global.css";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="create-session"
          options={{ presentation: "modal" }}
        />
        <Stack.Screen
          name="analysis/[id]"
          options={{ presentation: "modal" }}
        />
      </Stack>
    </>
  );
}
