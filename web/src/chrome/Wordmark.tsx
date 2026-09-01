/**
 * The lockup. Fraunces carries the expedition-journal character the brand
 * doc asks for; the tagline says what the product is, which the previous
 * subtitle (a database health readout) did not.
 */
export default function Wordmark() {
  return (
    <h1 className="flex min-w-0 shrink items-baseline gap-2 sm:gap-2.5">
      <span aria-hidden="true" className="text-brass-500">
        ✦
      </span>
      <span className="truncate font-display text-lg leading-none text-parchment-50 sm:text-xl">
        NameScape
      </span>
      <span className="hidden whitespace-nowrap text-xs leading-none text-parchment-400 lg:inline">
        the atlas of absurd place names
      </span>
    </h1>
  )
}
