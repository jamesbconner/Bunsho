import { Paper, SimpleGrid, Text } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';
import { formatPercent } from './format';

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={28} fw={600}>
        {value}
      </Text>
      {note !== undefined && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Paper>
  );
}

/** Reviews and new cards today, and how well what you know is holding up. */
export function TodayPanel({ stats }: { stats: StatsSummary }) {
  const { introduced_today: introduced, retention_30d: retention } = stats;
  const introducedTotal = introduced.kana + introduced.kanji + introduced.vocab;
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }}>
      <Figure label="Reviewed today" value={formatCount(stats.reviewed_today)} />
      <Figure
        label="New cards today"
        value={formatCount(introducedTotal)}
        note={`${introduced.kana} kana, ${introduced.kanji} kanji, ${introduced.vocab} vocabulary`}
      />
      <Figure
        label="Retention, last 30 days"
        value={retention === null ? 'Not enough reviews yet' : formatPercent(retention)}
        note="Reviews of cards you already knew that were graded Hard or better"
      />
    </SimpleGrid>
  );
}
