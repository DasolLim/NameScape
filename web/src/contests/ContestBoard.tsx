import { useCallback, useEffect, useState } from 'react'

import { castVote, fetchContest, proposeNickname, type ContestBoardData } from '../api/contests'
import { useAuth } from '../auth/store'
import Countdown from './Countdown'

const MAX_NICKNAME = 60

interface ContestBoardProps {
  placeId: number
}

export default function ContestBoard({ placeId }: ContestBoardProps) {
  const [board, setBoard] = useState<ContestBoardData | null>(null)
  const [draft, setDraft] = useState('')
  const requireAuth = useAuth((state) => state.requireAuth)
  // Voting and proposing need an account; claiming does not. Offering these
  // to a guest and refusing on click would be a trap, so they are disabled
  // and the reason is on screen next to them.
  const needsAccount = useAuth((state) => state.status !== 'signed-in')

  const reload = useCallback(() => {
    fetchContest(placeId)
      .then(setBoard)
      .catch(() => setBoard(null))
  }, [placeId])

  useEffect(reload, [reload])

  if (!board) return null

  const ranked = [...board.proposals].sort((a, b) => b.score - a.score)

  function vote(proposalId: number, value: 1 | -1) {
    requireAuth(() => {
      castVote(proposalId, value).then(reload).catch(reload)
    })
  }

  return (
    <section className="rounded-xl bg-[#151C28] p-5 ring-1 ring-[#2B3646]">
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm text-[#D6D0C2]">Nickname contest</h3>
        <Countdown closesAt={board.closes_at} />
      </header>

      {board.nickname && (
        <p className="mt-2 font-serif text-lg text-[#E8A33D]">&ldquo;{board.nickname}&rdquo;</p>
      )}

      <ul className="mt-4 space-y-3">
        {ranked.map((proposal) => {
          const own = proposal.is_yours
          const progress = Math.max(0, Math.min(proposal.score, board.quorum))
          return (
            <li key={proposal.id}>
              <article className="rounded-lg bg-[#1E2735] p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-sm text-[#F5F1E8]">{proposal.text}</p>
                  <span className="text-sm tabular-nums text-[#9B9484]">{proposal.score}</span>
                </div>

                <div
                  role="progressbar"
                  aria-label={`Progress to quorum for ${proposal.text}`}
                  aria-valuenow={proposal.score}
                  aria-valuemin={0}
                  aria-valuemax={board.quorum}
                  className="mt-2 h-1 w-full overflow-hidden rounded-full bg-[#2B3646]"
                >
                  <span
                    className="block h-full bg-[#E8A33D]"
                    style={{ width: `${(progress / board.quorum) * 100}%` }}
                  />
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={own || needsAccount}
                    onClick={() => vote(proposal.id, 1)}
                    aria-label={`Agree with ${proposal.text}`}
                    className="rounded-md px-2 py-1 text-xs text-[#35A48F] disabled:opacity-40"
                  >
                    ▲ Agree <span className="tabular-nums">{proposal.agree}</span>
                  </button>
                  <button
                    type="button"
                    disabled={own || needsAccount}
                    onClick={() => vote(proposal.id, -1)}
                    aria-label={`Disagree with ${proposal.text}`}
                    className="rounded-md px-2 py-1 text-xs text-[#C9524E] disabled:opacity-40"
                  >
                    ▼ Disagree <span className="tabular-nums">{proposal.disagree}</span>
                  </button>
                  {own && (
                    <span className="text-xs text-[#6B665C]">
                      Your own proposal — you cannot vote for it
                    </span>
                  )}
                </div>
              </article>
            </li>
          )
        })}
      </ul>

      <form
        className="mt-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (!draft.trim()) return
          requireAuth(() => {
            proposeNickname(placeId, draft)
              .then(() => {
                setDraft('')
                reload()
              })
              .catch(() => undefined)
          })
        }}
      >
        <label htmlFor="nickname-draft" className="block text-xs text-[#9B9484]">
          Propose a nickname
        </label>
        {needsAccount && (
          <p
            id="contest-needs-account"
            data-testid="needs-account"
            className="mt-1 text-xs text-parchment-400"
          >
            Naming and voting need an account. Claiming a place does not.
          </p>
        )}
        <input
          id="nickname-draft"
          value={draft}
          disabled={needsAccount}
          aria-describedby={needsAccount ? 'contest-needs-account' : undefined}
          maxLength={MAX_NICKNAME}
          onChange={(event) => setDraft(event.target.value.slice(0, MAX_NICKNAME))}
          className="mt-1 w-full rounded-lg bg-[#0E131C] px-3 py-2 text-sm text-[#F5F1E8] ring-1 ring-[#2B3646] focus:outline-none focus:ring-[#E8A33D]"
        />
        <p className="mt-1 text-right text-xs tabular-nums text-[#6B665C]">
          {MAX_NICKNAME - draft.length} left
        </p>
      </form>
    </section>
  )
}
