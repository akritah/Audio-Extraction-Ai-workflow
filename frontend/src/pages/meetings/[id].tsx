import { useRouter } from "next/router"
import { useEffect, useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { getMeeting, getMeetingStatus, icsDownloadUrl } from "@/lib/api"
import GraphView from "@/components/GraphView"

export default function MeetingDetail() {
  const router = useRouter()
  const { id } = router.query
  const [meeting, setMeeting] = useState<any>(null)
  const [status,  setStatus]  = useState("processing")
  const [tab,     setTab]     = useState("summary")

  // poll for completion
  useEffect(() => {
    if (!id) return
    const mid = Number(id)

    const poll = setInterval(async () => {
      const s = await getMeetingStatus(mid).catch(() => ({ status: "processing" }))
      setStatus(s.status)
      if (s.status === "done") {
        clearInterval(poll)
        const m = await getMeeting(mid)
        setMeeting(m)
      } else if (s.status === "failed") {
        clearInterval(poll)
      }
    }, 3000)

    return () => clearInterval(poll)
  }, [id])

  const tabs = ["summary", "transcript", "tasks", "events", "graph"]

  return (
    <>
      <Head><title>Meeting {id}</title></Head>
      <div className="min-h-screen bg-paper">
        <header className="border-b border-border px-8 py-4 flex items-center gap-4">
          <Link href="/" className="font-mono text-sm text-muted hover:text-accent">← Back</Link>
          <span className="font-serif text-xl">{meeting?.filename || `Meeting #${id}`}</span>
        </header>

        <main className="max-w-5xl mx-auto px-8 py-10">
          {status === "processing" && (
            <div className="border border-border bg-white p-8 text-center">
              <div className="font-mono text-muted animate-pulse">Processing audio pipeline…</div>
              <div className="text-xs text-muted mt-2">Transcription → Diarization → Extraction → Indexing</div>
            </div>
          )}

          {status === "failed" && (
            <div className="border border-accent/40 bg-accent/5 p-6 text-accent font-mono text-sm">
              Processing failed. Check backend logs.
            </div>
          )}

          {status === "done" && meeting && (
            <>
              {/* tab bar */}
              <div className="flex gap-1 mb-6 border-b border-border">
                {tabs.map(t => (
                  <button key={t} onClick={() => setTab(t)}
                    className={`px-4 py-2 font-mono text-sm capitalize
                      ${tab === t
                        ? "border-b-2 border-accent text-accent"
                        : "text-muted hover:text-ink"}`}>
                    {t}
                  </button>
                ))}
              </div>

              {/* summary */}
              {tab === "summary" && (
                <div className="bg-white border border-border p-6 whitespace-pre-wrap text-sm leading-relaxed">
                  {meeting.summary}
                </div>
              )}

              {/* transcript */}
              {tab === "transcript" && (
                <div className="bg-white border border-border divide-y divide-border max-h-[600px] overflow-y-auto">
                  {(meeting.transcript || []).map((seg: any, i: number) => (
                    <div key={i} className="px-5 py-3 flex gap-4">
                      <span className="font-mono text-xs text-muted w-20 shrink-0 pt-0.5">
                        {seg.speaker}
                      </span>
                      <span className="text-sm">{seg.text}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* tasks */}
              {tab === "tasks" && (
                <div className="border border-border bg-white divide-y divide-border">
                  {meeting.tasks?.length === 0 && (
                    <p className="p-5 text-sm text-muted">No tasks extracted.</p>
                  )}
                  {meeting.tasks?.map((t: any) => (
                    <div key={t.id} className="px-5 py-4 flex justify-between items-start">
                      <div>
                        <p className="font-medium text-sm">{t.task}</p>
                        <p className="text-xs text-muted font-mono mt-1">
                          {t.owner || "Unassigned"} • {t.deadline || "No deadline"}
                        </p>
                      </div>
                      <span className={`text-xs font-mono px-2 py-1 border
                        ${t.status === "Done"
                          ? "border-green-400 text-green-700"
                          : "border-accent/40 text-accent"}`}>
                        {t.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* calendar events */}
              {tab === "events" && (
                <div className="border border-border bg-white divide-y divide-border">
                  {meeting.events?.length === 0 && (
                    <p className="p-5 text-sm text-muted">No scheduled events detected.</p>
                  )}
                  {meeting.events?.map((ev: any) => (
                    <div key={ev.id} className="px-5 py-4 flex justify-between items-center">
                      <div>
                        <p className="font-medium">{ev.title}</p>
                        <p className="text-xs font-mono text-muted">{ev.event_date} {ev.event_time}</p>
                      </div>
                      <a href={icsDownloadUrl(ev.id)}
                        className="text-xs font-mono border border-border px-3 py-1 hover:border-accent hover:text-accent transition-colors">
                        Download .ics
                      </a>
                    </div>
                  ))}
                </div>
              )}

              {/* knowledge graph */}
              {tab === "graph" && (
                <div className="border border-border bg-white h-[500px]">
                  <GraphView data={meeting.graph} />
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </>
  )
}
