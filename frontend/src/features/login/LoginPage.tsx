import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { Navigate, useLocation } from 'react-router';

import { ApiError, messageFor } from '../../api/errors';
import { useAuth } from '../../auth/authContext';
import { useCountdown } from '../../hooks/useCountdown';
import { returnPath } from './returnPath';

type LoginField = 'username' | 'password';
const LOGIN_FIELDS: readonly LoginField[] = ['username', 'password'];

/** The server's per-field messages for the two login inputs; empty when it named neither. */
function loginFieldErrors(error: ApiError): Partial<Record<LoginField, string>> {
  const fields: Partial<Record<LoginField, string>> = {};
  for (const name of LOGIN_FIELDS) {
    const message = error.fieldErrors[name];
    if (message !== undefined) fields[name] = message;
  }
  return fields;
}

export function LoginPage() {
  const { status, sessionExpired, login } = useAuth();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { remaining, start } = useCountdown();
  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { username: '', password: '' },
    validate: {
      username: (value) => (value.trim() === '' ? 'Enter your username' : null),
      password: (value) => (value === '' ? 'Enter your password' : null),
    },
  });

  if (status === 'authenticated') {
    return <Navigate to={returnPath(location.state)} replace />;
  }

  const submit = form.onSubmit(async (values) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(values.username.trim(), values.password);
    } catch (caught) {
      const fields =
        caught instanceof ApiError && caught.status === 422 ? loginFieldErrors(caught) : {};
      if (caught instanceof ApiError && caught.status === 401) {
        setError('Invalid username or password.');
      } else if (Object.keys(fields).length > 0) {
        form.setErrors(fields);
        // The first rejected field, in form order, gets the cursor.
        const first = LOGIN_FIELDS.find((name) => name in fields);
        if (first !== undefined) form.getInputNode(first)?.focus();
      } else {
        if (caught instanceof ApiError && caught.status === 429) {
          start(caught.retryAfterSeconds ?? 30);
        }
        setError(messageFor(caught));
      }
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" radius="md" w={380} maw="100%">
        <form
          onSubmit={(event) => {
            void submit(event);
          }}
          noValidate
        >
          <Stack>
            <Title order={2}>
              Bunshō <span lang="ja">文章</span>
            </Title>
            {sessionExpired && (
              <Alert color="yellow" title="Signed out">
                Your session has expired. Please log in again.
              </Alert>
            )}
            {error !== null && (
              <Alert color="red" role="alert">
                {error}
              </Alert>
            )}
            {remaining > 0 && (
              // Visual only: the alert above is announced once, a ticking number would repeat.
              <Text size="sm" c="dimmed" aria-hidden="true">
                You can try again in {String(remaining)} s.
              </Text>
            )}
            <TextInput
              label="Username"
              autoComplete="username"
              autoFocus
              key={form.key('username')}
              {...form.getInputProps('username')}
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              key={form.key('password')}
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={submitting} disabled={remaining > 0}>
              Log in
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
