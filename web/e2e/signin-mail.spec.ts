import { expect, test, type APIRequestContext } from '@playwright/test'

/** Mailpit, the local inbox that `make dev` and CI both point SMTP at. */
const INBOX = process.env.MAIL_INBOX_URL ?? 'http://localhost:8025'

async function linkFromInbox(request: APIRequestContext, email: string): Promise<string> {
  const found = await request.get(`${INBOX}/api/v1/search?query=to:${email}`)
  expect(found.ok(), 'the local inbox should be reachable').toBeTruthy()

  const { messages } = (await found.json()) as { messages: { ID: string }[] }
  expect(messages.length, `no sign-in mail arrived for ${email}`).toBeGreaterThan(0)

  const message = await request.get(`${INBOX}/api/v1/message/${messages[0]!.ID}`)
  const body = (await message.json()) as { Text?: string; HTML?: string }
  const link = /http:\/\/localhost:5173\/\?token=[\w-]+/.exec(
    `${body.Text ?? ''}${body.HTML ?? ''}`,
  )?.[0]

  expect(link, 'the mail should carry a sign-in link').toBeTruthy()
  return link!
}

test('a sign-in link is really mailed, and really signs you in', async ({ page, request }) => {
  test.slow()
  const email = `finder-${Date.now()}@example.com`

  await page.goto('/')
  await page.getByRole('button', { name: /^sign in$/i }).click()
  await page.getByLabel(/email/i).fill(email)
  await page.getByRole('button', { name: /send me a link/i }).click()
  await expect(page.getByText(/check your email/i)).toBeVisible()

  // Mail must actually exist. Logging the link instead of sending it is the
  // bug this test is here to prevent.
  await expect
    .poll(
      async () =>
        (
          (await (await request.get(`${INBOX}/api/v1/search?query=to:${email}`)).json()) as {
            messages: unknown[]
          }
        ).messages.length,
      { timeout: 20_000, message: 'waiting for the sign-in mail' },
    )
    .toBeGreaterThan(0)

  await page.goto(await linkFromInbox(request, email))

  // Signed in, and the spent token is gone from the address bar.
  await expect(page.getByRole('button', { name: /^@finder/i })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('token')).toBeNull()
})
