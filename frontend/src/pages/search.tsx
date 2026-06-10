import { useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { search } from "@/lib/api"

export default function SearchPage() {
  const [query,   setQuery]   = useState("")
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  async function run() {
    if (!query.trim()) return
    setLoading(true)
    const res = await search(query).catch(() => [])
    setResults(res)
    setLoading(false)
  }

  return (
    <>
      <Head><title>Search — Meeting Intelligence</title></Head>
      <div className="min-h-screen bg-paper">
        <header className="border-b border-border px-8 py-4 flex items-center gap-4">
          <Link href="/" className="font-mono text-sm text-muted hover:text-accent">← Dashboard</Link>
          <span className="font-serif text-xl">Semantic Search</span>
        </header>

        <main className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && run()}
              placeholder="Show all tasks assigned to Priya…"
              className="flex-1 border border-border px-4 py-3 font-mono text-sm bg-white focus:outline-none focus:border-accent"
            />
            <button
              onClick={run}
              disabled={loading}
              className="border border-ink px-6 font-mono text-sm hover:bg-ink hover:text-paper transition-colors disabled:opacity-40">
              {loading ? "…" : "Search"}
            </button>
          </div>

          {results.length > 0 && (
            <div className="border border-border bg-white divide-y divide-border">
              {results.map((r, i) => (
                <div key={i} className="px-5 py-4">
                  <div className="flex justify-between items-start mb-1">
                    <span className={`text-xs font-mono px-2 py-0.5 border
                      ${r.type === "task"     ? "border-green-300 text-green-700" :
                        r.type === "summary"  ? "border-blue-300  text-blue-700"  :
                        "border-border text-muted"}`}>
                      {r.type}
                    </span>
                    <span className="font-mono text-xs text-muted">{r.score}</span>
                  </div>
                  <p className="text-sm mt-1">{r.text}</p>
                  {r.meeting?.filename && (
                    <Link href={`/meetings/${r.meeting_id}`}
                      className="text-xs font-mono text-accent hover:underline mt-1 block">
                      → {r.meeting.filename}
                    </Link>
                  )}
                </div>
              ))}
            </div>
          )}

          {results.length === 0 && !loading && query && (
            <p className="text-muted font-mono text-sm">No results found.</p>
          )}
        </main>
      </div>
    </>
  )
}
