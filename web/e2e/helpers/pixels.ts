import type { Page } from '@playwright/test'

/** Sample the globe's own GL buffer. PNG bytes are useless for "how different". */
export async function samplePixels(page: Page): Promise<number[]> {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas.maplibregl-canvas') as HTMLCanvasElement | null
    if (!canvas) throw new Error('no globe canvas')
    const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl')
    if (!gl) throw new Error('no webgl context')

    const buffer = new Uint8Array(canvas.width * canvas.height * 4)
    gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, buffer)

    const sampled: number[] = []
    for (let i = 0; i < buffer.length; i += 4 * 1013) {
      sampled.push(buffer[i] ?? 0, buffer[i + 1] ?? 0, buffer[i + 2] ?? 0)
    }
    return sampled
  })
}

/** Fraction of sampled channels that moved by more than a rounding wobble. */
export function fractionChanged(before: number[], after: number[]): number {
  let changed = 0
  for (let i = 0; i < before.length; i += 1) {
    if (Math.abs((before[i] ?? 0) - (after[i] ?? 0)) > 4) changed += 1
  }
  return changed / Math.max(before.length, 1)
}
