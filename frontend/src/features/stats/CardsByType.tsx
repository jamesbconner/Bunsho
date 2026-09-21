import { Table } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatCount } from '../build/format';

const TYPES = [
  { key: 'kana', label: 'Kana' },
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/** How many cards of each type are being learned, known, or being relearned. */
export function CardsByType({ byType }: { byType: StatsSummary['by_type'] }) {
  return (
    <Table withTableBorder aria-label="Cards by type and state">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Type</Table.Th>
          <Table.Th ta="right">Total</Table.Th>
          <Table.Th ta="right">Learning</Table.Th>
          <Table.Th ta="right">Review</Table.Th>
          <Table.Th ta="right">Relearning</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {TYPES.map(({ key, label }) => {
          const row = byType[key];
          return (
            <Table.Tr key={key}>
              <Table.Td>{label}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.total ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.learning ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.review ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(row?.relearning ?? 0)}</Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
