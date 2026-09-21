import { Group, Progress, Stack, Text, Title } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';

const TYPES = [
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/**
 * Progress through each JLPT level (kana has no levels): a two-tone bar of the cards in Review and
 * the cards introduced but not yet in Review, with the numbers beside it so the bar is never the
 * only carrier. Levels with nothing in them are left out.
 */
export function LevelProgress({ byLevel }: { byLevel: StatsSummary['by_level'] }) {
  return (
    <Stack gap="lg">
      {TYPES.map(({ key, label }) => {
        const levels = byLevel.filter((row) => row.item_type === key && row.total > 0);
        if (levels.length === 0) return null;
        return (
          <Stack key={key} gap="xs" component="section" aria-label={`${label} progress by level`}>
            <Title order={4}>{label}</Title>
            {levels.map((row) => {
              const known = (row.review / row.total) * 100;
              const learning = (Math.max(row.introduced - row.review, 0) / row.total) * 100;
              return (
                <Group key={row.level} wrap="nowrap" gap="md" align="center">
                  <Text w={36} fw={500}>
                    {row.level}
                  </Text>
                  <Progress.Root size="lg" style={{ flex: 1 }} aria-hidden="true">
                    <Progress.Section value={known} color="indigo" />
                    <Progress.Section value={learning} color="indigo.2" />
                  </Progress.Root>
                  <Text size="sm" c="dimmed" w={{ base: 130, sm: 260 }}>
                    {formatCount(row.review)} in review, {formatCount(row.introduced)} of{' '}
                    {formatCount(row.total)} introduced
                  </Text>
                </Group>
              );
            })}
          </Stack>
        );
      })}
    </Stack>
  );
}
