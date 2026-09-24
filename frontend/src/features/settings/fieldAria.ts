/** The ids of a `Input.Wrapper`'s label, description and (when shown) error, for a group's aria. */
export function groupAria(id: string, hasError: boolean) {
  return {
    role: 'group',
    'aria-labelledby': `${id}-label`,
    'aria-describedby': hasError ? `${id}-error ${id}-description` : `${id}-description`,
  };
}
