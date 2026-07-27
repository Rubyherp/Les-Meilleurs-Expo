# Safe-Area Layout Design

## Goal

Keep route content clear of device notches, status bars, and home indicators
without adding duplicate padding around the tab navigator or modal screens.

## Approach

- Add `SafeAreaProvider` once in `app/_layout.tsx`.
- Use `SafeAreaView` from `react-native-safe-area-context` at each route's
  content boundary.
- Tab screens use `edges={["top"]}` because the tab bar manages its own bottom
  safe area.
- Modal and full-screen routes use `edges={["top", "bottom"]}`.
- Preserve existing `ScrollView` behavior, class-based padding, camera preview
  dimensions, and visual hierarchy.
- Do not nest additional safe-area views inside a route unless a component is
  independently rendered outside the route boundary.

## Routes in scope

- `(tabs)/practice`
- `(tabs)/groups`
- `(tabs)/profile`
- `create-session`
- `create-mode-a`
- `create-mode-b`
- `analysis/[id]`

## Verification

- TypeScript compilation with `npx tsc --noEmit`.
- Search all route files to confirm the intended boundaries are wrapped.
- Run the existing focused standalone tests.
- Confirm no route receives both root and local safe-area padding.

## Non-goals

- No redesign of spacing or typography.
- No navigator/tab-bar replacement.
- No changes to analysis, camera, or media behavior.
