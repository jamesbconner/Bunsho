import {
  Alert,
  Button,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { Link } from 'react-router';

import { messageFor } from '../../api/errors';
import { useContentSummary } from '../../api/queries';
import { formatCount } from '../build/format';

const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={28} fw={600}>
        {formatCount(value)}
      </Text>
      {note !== undefined && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Paper>
  );
}

/** What has been built so far, or an invitation to build it. */
export function HomePage() {
  const summary = useContentSummary();

  if (summary.isPending) {
    return (
      <Stack>
        <Skeleton height={32} width={220} />
        <Skeleton height={112} />
      </Stack>
    );
  }
  if (summary.isError) {
    return (
      <Alert color="red" title="Couldn't load the content summary">
        <Text size="sm">{messageFor(summary.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void summary.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const data = summary.data;
  if (!data.built) {
    return (
      <Alert color="blue" title="Welcome to Bunshō">
        <Text size="sm">
          There is no study content yet. Build it once from the vocabulary deck and it will be here.
        </Text>
        <Button component={Link} to="/build" mt="sm" size="xs">
          Build your content
        </Button>
      </Alert>
    );
  }

  return (
    <Stack gap="md">
      <Title order={2}>Your content</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Stat label="Kana" value={data.kana} />
        <Stat
          label="Kanji"
          value={data.kanji}
          note={`${formatCount(data.unleveled_kanji)} not in the JLPT vocabulary`}
        />
        <Stat label="Vocabulary" value={data.vocab} />
      </SimpleGrid>
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
              <Table.Td ta="right">{formatCount(data.vocab_by_level[level] ?? 0)}</Table.Td>
              <Table.Td ta="right">{formatCount(data.kanji_by_level[level] ?? 0)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
