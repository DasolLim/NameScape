import type { components } from './schema'

export type ContestBoardData = components['schemas']['ContestBoard']
export type ProposalData = components['schemas']['ProposalResponse']

export async function fetchContest(placeId: number): Promise<ContestBoardData> {
  const response = await fetch(`/api/contests/${placeId}`)
  if (!response.ok) throw new Error(`contest lookup failed: ${response.status}`)
  return (await response.json()) as ContestBoardData
}

export async function castVote(proposalId: number, value: 1 | -1): Promise<void> {
  const response = await fetch('/api/votes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proposal_id: proposalId, value }),
  })
  if (!response.ok) throw new Error(`vote failed: ${response.status}`)
}

export async function proposeNickname(placeId: number, text: string): Promise<ProposalData> {
  const response = await fetch('/api/proposals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ place_id: placeId, text }),
  })
  if (!response.ok) throw new Error(`proposal failed: ${response.status}`)
  return (await response.json()) as ProposalData
}
