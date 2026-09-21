import { Center, Loader } from '@mantine/core';

/** Shown while a page's code is being fetched (the pages load on demand). */
export function PageLoader() {
  return (
    <Center py="xl">
      <Loader role="status" aria-label="Loading page" />
    </Center>
  );
}
