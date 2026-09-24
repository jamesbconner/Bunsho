import { Alert, Button, Skeleton, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import { ApiError, messageFor } from '../../api/errors';
import { useStatsSummary } from '../../api/queries';
import { CardsByType } from './CardsByType';
import { LevelProgress } from './LevelProgress';
import { ReviewsChart } from './ReviewsChart';
import { TodayPanel } from './TodayPanel';

/** How you are doing: today's numbers, the last 30 days, and progress through the levels. */
export function StatsPage() {
  const stats = useStatsSummary();

  if (stats.isPending) {
    return (
      <Stack>
        <Skeleton height={32} width={220} />
        <Skeleton height={112} />
        <Skeleton height={240} />
      </Stack>
    );
  }
  if (stats.isError) {
    if (stats.error instanceof ApiError && stats.error.status === 503) {
      return (
        <Alert color="blue" title="Nothing to show yet">
          <Text size="sm">The study content has not been built yet.</Text>
          <Button component={Link} to="/settings?tab=system" mt="sm" size="xs">
            Build your content
          </Button>
        </Alert>
      );
    }
    return (
      <Alert color="red" title="Couldn't load your statistics">
        <Text size="sm">{messageFor(stats.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void stats.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const data = stats.data;
  return (
    <Stack gap="xl">
      <Title order={2}>Statistics</Title>
      <TodayPanel stats={data} />
      <Stack gap="sm">
        <Title order={3}>Last 30 days</Title>
        <ReviewsChart days={data.daily_reviews} />
      </Stack>
      <Stack gap="sm">
        <Title order={3}>Your cards</Title>
        <CardsByType byType={data.by_type} />
      </Stack>
      <Stack gap="sm">
        <Title order={3}>Progress by level</Title>
        <LevelProgress byLevel={data.by_level} />
      </Stack>
    </Stack>
  );
}
