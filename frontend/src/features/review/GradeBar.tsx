import { Button, SimpleGrid } from '@mantine/core';
import type { Ref } from 'react';

import type { Grade, GradeIntervals } from '../../api/endpoints';
import { formatInterval } from './formatInterval';
import classes from './review.module.css';

interface GradeChoice {
  grade: Grade;
  label: string;
  key: string;
  interval: keyof GradeIntervals;
}

const GRADES: readonly GradeChoice[] = [
  { grade: 1, label: 'Again', key: '1', interval: 'again' },
  { grade: 2, label: 'Hard', key: '2', interval: 'hard' },
  { grade: 3, label: 'Good', key: '3', interval: 'good' },
  { grade: 4, label: 'Easy', key: '4', interval: 'easy' },
];

interface GradeBarProps {
  intervals: GradeIntervals;
  disabled: boolean;
  onGrade: (grade: Grade) => void;
  /**
   * The group itself takes focus after the flip. It is not a button, so a key still held down
   * from the flip cannot press a grade.
   */
  groupRef: Ref<HTMLDivElement>;
}

/** The four grade buttons with their keys and the projected next interval of each. */
export function GradeBar({ intervals, disabled, onGrade, groupRef }: GradeBarProps) {
  return (
    <div
      ref={groupRef}
      role="group"
      aria-label="Grade your answer"
      tabIndex={-1}
      className={classes.grades}
      data-review-controls
    >
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
        {GRADES.map(({ grade, label, key, interval }) => (
          <Button
            key={grade}
            variant={grade === 3 ? 'filled' : 'light'}
            color={grade === 1 ? 'red' : undefined}
            size="md"
            disabled={disabled}
            aria-keyshortcuts={key}
            onClick={() => {
              onGrade(grade);
            }}
          >
            <span className={classes.key} aria-hidden="true">
              {key}
            </span>
            {label} · {formatInterval(intervals[interval])}
          </Button>
        ))}
      </SimpleGrid>
    </div>
  );
}
