import { SegmentedControl, useMantineColorScheme } from '@mantine/core';

/** Light, dark or follow the system. Mantine remembers the choice in localStorage. */
export function ColorSchemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <SegmentedControl
      size="xs"
      aria-label="Colour theme"
      value={colorScheme}
      onChange={(value) => {
        if (value === 'light' || value === 'dark' || value === 'auto') setColorScheme(value);
      }}
      data={[
        { label: 'Light', value: 'light' },
        { label: 'Dark', value: 'dark' },
        { label: 'Auto', value: 'auto' },
      ]}
    />
  );
}
