import { useEffect, useState } from 'react'

import {
  fetchMyDiscoveries,
  fetchPassport,
  shareCardUrl,
  type PassportData,
  type UserDiscovery,
} from '../api/passport'
import CompletionRing from './CompletionRing'

interface PassportProps {
  username: string
  onClose: () => void
}

export default function Passport({ username, onClose }: PassportProps) {
  const [data, setData] = useState<PassportData | null>(null)
  const [finds, setFinds] = useState<UserDiscovery[]>([])

  useEffect(() => {
    fetchPassport(username)
      .then(setData)
      .catch(() => setData(null))
    fetchMyDiscoveries()
      .then(setFinds)
      .catch(() => setFinds([]))
  }, [username])

  if (!data) return null

  return (
    <section className="w-[min(34rem,92vw)] rounded-xl bg-[#151C28] p-6 text-left ring-1 ring-[#2B3646]">
      <header className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#9B9484]">Passport</p>
          <p className="font-serif text-xl text-[#F5F1E8]">@{data.username}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close passport"
          className="rounded-full px-3 py-1 text-[#9B9484] hover:text-[#F5F1E8]"
        >
          ✕
        </button>
      </header>

      <p
        data-testid="first-finds"
        aria-describedby="first-finds-label"
        className="mt-5 font-serif text-5xl tabular-nums text-[#E8A33D]"
      >
        {data.first_finds}
      </p>
      <p id="first-finds-label" className="text-sm text-[#9B9484]">
        places found first
      </p>

      {Object.keys(data.countries).length > 0 && (
        <div className="mt-5 flex flex-wrap gap-4">
          {Object.entries(data.countries).map(([country, found]) => (
            <CompletionRing
              key={country}
              country={country}
              found={found}
              completion={data.completion[country] ?? 0}
            />
          ))}
        </div>
      )}

      {finds.length > 0 ? (
        <ul className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {finds.map((find) => (
            <li
              key={find.id}
              data-testid="stamp-tile"
              className="rounded-lg bg-[#1E2735] p-3 ring-1 ring-[#2B3646]"
            >
              <p className="text-sm text-[#F5F1E8]">{find.place_name}</p>
              <p className="mt-1 text-xs text-[#9B9484]">{find.country_code ?? '—'}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-6 text-sm text-[#9B9484]">
          No stamps yet — find a place nobody has claimed and be the first.
        </p>
      )}

      <a
        href={shareCardUrl(data.username)}
        target="_blank"
        rel="noreferrer"
        className="mt-6 inline-block rounded-lg bg-[#E8A33D] px-4 py-2 text-sm font-medium text-[#4A320F]"
      >
        Share card
      </a>
    </section>
  )
}
