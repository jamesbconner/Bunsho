import '@mantine/charts/styles.css';

import { BarChart } from '@mantine/charts';
import { Text, VisuallyHidden } from '@mantine/core';

import type { StatsSummary } from '../../api/endpoints';
import { formatShortDay } from './format';

/**
 * Reviews per day for the last 30 study days. The chart is decoration for sighted users
 * (`aria-hidden`); the same numbers are in a visually hidden table for everyone else.
 */
export function ReviewsChart({ days }: { days: StatsSummary['daily_reviews'] }) {
  if (days.every((day) => day.reviews === 0)) {
    return <Text c="dimmed">No reviews yet: study a few cards and they will appear here.</Text>;
  }
  const rows = days.map((day) => ({ label: formatShortDay(day.day), reviews: day.reviews }));
  return (
    <>
      <div aria-hidden="true">
        <BarChart
          h={240}
          data={rows}
          dataKey="label"
          series={[{ name: 'reviews', label: 'Reviews', color: 'indigo.6' }]}
          tickLine="y"
          withLegend={false}
          accessibilityLayer={false}
          yAxisProps={{ allowDecimals: false }}
        />
      </div>
      <VisuallyHidden>
        <table aria-label="Reviews per day, last 30 days">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Reviews</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td>{row.reviews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </VisuallyHidden>
    </>
  );
}
