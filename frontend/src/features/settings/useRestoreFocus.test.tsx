import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useRestoreFocus } from './useRestoreFocus';

function addInput(): HTMLInputElement {
  const input = document.createElement('input');
  document.body.append(input);
  return input;
}

describe('useRestoreFocus', () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it('gives focus back to the remembered field once the lock ends', () => {
    const input = addInput();
    input.focus();
    const { result, rerender } = renderHook(({ locked }) => useRestoreFocus(locked), {
      initialProps: { locked: false },
    });

    result.current();
    rerender({ locked: true });
    input.blur();
    expect(document.body).toHaveFocus();
    rerender({ locked: false });

    expect(input).toHaveFocus();
  });

  it('does not take focus from something else that has it', () => {
    const remembered = addInput();
    const other = addInput();
    remembered.focus();
    const { result, rerender } = renderHook(({ locked }) => useRestoreFocus(locked), {
      initialProps: { locked: false },
    });

    result.current();
    rerender({ locked: true });
    other.focus();
    rerender({ locked: false });

    expect(other).toHaveFocus();
  });

  it('does nothing when the remembered field is gone', () => {
    const input = addInput();
    input.focus();
    const { result, rerender } = renderHook(({ locked }) => useRestoreFocus(locked), {
      initialProps: { locked: false },
    });

    result.current();
    rerender({ locked: true });
    input.remove();
    rerender({ locked: false });

    expect(document.body).toHaveFocus();
  });

  it('remembers a field only for one lock', () => {
    const input = addInput();
    input.focus();
    const { result, rerender } = renderHook(({ locked }) => useRestoreFocus(locked), {
      initialProps: { locked: false },
    });

    result.current();
    rerender({ locked: true });
    rerender({ locked: false });
    input.blur();
    rerender({ locked: true });
    rerender({ locked: false });

    expect(document.body).toHaveFocus();
  });
});
