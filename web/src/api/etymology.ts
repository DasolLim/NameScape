import type { components } from './schema'

export type CorrectionResponse = components['schemas']['CorrectionResponse']

export class CorrectionError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** File a correction. Held for review, never applied on the spot. */
export async function correctEtymology(
  placeId: number,
  text: string,
): Promise<CorrectionResponse> {
  const response = await fetch(`/api/places/${placeId}/etymology`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new CorrectionError(body.detail ?? 'That did not work.', response.status)
  }
  return (await response.json()) as CorrectionResponse
}
