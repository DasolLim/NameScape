import type { components } from './schema'

export type PuzzleState = components['schemas']['PuzzleStateResponse']
export type PuzzleGuess = components['schemas']['PuzzleGuessResponse']
export type PuzzleAnswer = components['schemas']['PuzzleAnswerResponse']
export type ArchiveEntry = components['schemas']['ArchiveEntry']

export class PuzzleError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function orThrow(response: Response): Promise<unknown> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new PuzzleError(body.detail ?? 'That did not work.', response.status)
  }
  return response.json()
}

/** Today's puzzle and this player's progress, or null on a day without one. */
export async function fetchPuzzle(): Promise<PuzzleState | null> {
  return (await orThrow(await fetch('/api/puzzle'))) as PuzzleState | null
}

export async function submitGuess(puzzleId: number, placeId: number): Promise<PuzzleState> {
  const response = await fetch(`/api/puzzle/${puzzleId}/guess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ place_id: placeId }),
  })
  return (await orThrow(response)) as PuzzleState
}

export async function fetchArchive(): Promise<ArchiveEntry[]> {
  const body = (await orThrow(await fetch('/api/puzzle/archive'))) as {
    puzzles: ArchiveEntry[]
  }
  return body.puzzles
}
