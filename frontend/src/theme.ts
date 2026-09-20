import { createTheme } from '@mantine/core';

/** UI font stack: Latin text first, then the Japanese system fonts of macOS, Windows and Linux. */
export const UI_FONT_FAMILY =
  "system-ui, -apple-system, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic UI', 'Noto Sans JP', sans-serif";

export const theme = createTheme({
  fontFamily: UI_FONT_FAMILY,
  headings: { fontFamily: UI_FONT_FAMILY },
  primaryColor: 'indigo',
});
