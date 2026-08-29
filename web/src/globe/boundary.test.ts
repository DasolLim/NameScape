// @vitest-environment node
import { ESLint } from 'eslint'
import { expect, test } from 'vitest'

const IMPORT = "import maplibregl from 'maplibre-gl'\nexport default maplibregl\n"

async function ruleIdsFor(filePath: string): Promise<(string | null)[]> {
  const [result] = await new ESLint().lintText(IMPORT, { filePath })
  return (result?.messages ?? []).map((message) => message.ruleId)
}

test('maplibre-gl is banned outside src/globe', async () => {
  expect(await ruleIdsFor('src/components/SearchOverlay.ts')).toContain('no-restricted-imports')
})

test('maplibre-gl is allowed inside src/globe', async () => {
  expect(await ruleIdsFor('src/globe/internal.ts')).not.toContain('no-restricted-imports')
})
