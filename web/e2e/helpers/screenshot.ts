import type { Page, TestInfo } from '@playwright/test'

/** Capture to e2e/__screenshots__/<project>-<name>.png for visual review. */
export async function screenshot(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  await page.screenshot({
    path: `e2e/__screenshots__/${testInfo.project.name}-${name}.png`,
    fullPage: true,
  })
}
