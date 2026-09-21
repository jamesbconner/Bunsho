import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { segment } from '../test/fixtures';
import { Furigana } from './Furigana';

describe('Furigana', () => {
  it('puts each reading in a ruby element over its base text', () => {
    const { container } = render(<Furigana segments={[segment('食', 'た'), segment('べる')]} />);
    const ruby = container.querySelector('ruby');
    expect(ruby).toHaveTextContent('食(た)');
    expect(ruby?.querySelector('rt')).toHaveTextContent('た');
    expect(container).toHaveTextContent('食(た)べる');
  });

  it('keeps the parentheses fallback for browsers without ruby support', () => {
    const { container } = render(<Furigana segments={[segment('日', 'ひ')]} />);
    expect(container.querySelectorAll('rp')).toHaveLength(2);
  });

  it('shows segments without a reading as plain text', () => {
    const { container } = render(
      <Furigana segments={[segment('を'), segment('。', ''), segment('ね')]} />,
    );
    expect(container.querySelector('ruby')).toBeNull();
    expect(container).toHaveTextContent('を。ね');
  });

  it('marks the whole run as Japanese and flags the highlighted segment', () => {
    const { container } = render(
      <Furigana segments={[segment('食べる', null, true), segment('よ')]} />,
    );
    expect(container.firstElementChild).toHaveAttribute('lang', 'ja');
    const spans = container.querySelectorAll('span span');
    expect(spans).toHaveLength(2);
    expect(spans[0]).toHaveAttribute('data-highlighted', 'true');
    expect(spans[1]).not.toHaveAttribute('data-highlighted');
  });
});
