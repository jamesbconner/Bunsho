import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('renders the wordmark with the Japanese run marked as Japanese', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bunshō');
    expect(screen.getByTestId('wordmark-ja')).toHaveAttribute('lang', 'ja');
  });
});
