import { List, Stack, Table, Text } from '@mantine/core';

import type { BuildStatus } from '../../api/endpoints';
import { formatCount } from './format';

const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;

/** The result of a finished build: counts per JLPT level and the totals. */
export function BuildReportTable({ report }: { report: NonNullable<BuildStatus['report']> }) {
  return (
    <Stack gap="sm">
      {report.dry_run && (
        <Text size="sm" c="dimmed">
          Dry run: nothing was written.
        </Text>
      )}
      <Table withTableBorder aria-label="Items per JLPT level">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Level</Table.Th>
            <Table.Th ta="right">Vocabulary</Table.Th>
            <Table.Th ta="right">Kanji</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {LEVELS.map((level) => (
            <Table.Tr key={level}>
              <Table.Td>{level}</Table.Td>
              <Table.Td ta="right">{formatCount(report.vocab_by_level[level] ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(report.kanji_by_level[level] ?? 0)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <List size="sm" spacing={2}>
        <List.Item>{formatCount(report.kana_count)} kana</List.Item>
        <List.Item>{formatCount(report.vocab_count)} vocabulary items</List.Item>
        <List.Item>
          {formatCount(report.kanji_count)} kanji ({formatCount(report.unleveled_kanji_count)} not
          in the JLPT vocabulary)
        </List.Item>
        <List.Item>{formatCount(report.sentence_count)} example sentences</List.Item>
        <List.Item>Finished in {report.duration_seconds.toFixed(1)} seconds</List.Item>
      </List>
    </Stack>
  );
}
