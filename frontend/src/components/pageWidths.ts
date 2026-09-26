/** The two page widths, in px: focused pages are narrow, dashboards are wide. */
export const PAGE_WIDTHS = { narrow: 720, wide: 1100 } as const;

export type PageWidthName = keyof typeof PAGE_WIDTHS;
