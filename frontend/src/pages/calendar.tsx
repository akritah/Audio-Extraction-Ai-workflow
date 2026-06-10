import { useEffect, useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { getCalendarEvents, icsDownloadUrl } from "@/lib/api"

export default function CalendarPage() {
  const [events, setEvents] = useState<any[]>([])

  useEffect(() => {
    getCalendarEvents().then(setEvents).catch(console.error)
  }, [])

  return (
    <>
      <Head><title>Calendar — Meeting Intelligence</title></Head>
      <div className="min-h-screen bg-paper">
        <header className="border-b border-border px-8 py-4 flex items-center gap-4">
          <Link href="/" className="font-mono text-sm text-muted hover:text-accent">← Dashboard</Link>
          <span className="font-serif text-xl">Scheduled Events</span>
        </header>

        <main className="max-w-4xl mx-auto px-8 py-10">
          {events.length === 0
            ? <p className="text-muted text-sm font-mono">No calendar events extracted yet.</p>
            : (
              <div className="border border-border bg-white divide-y divide-border">
                {events.map((ev: any) => (
                  <div key={ev.id} className="px-5 py-4 flex justify-between items-center">
                    <div>
                      <p className="font-medium">{ev.title}</p>
                      <p className="font-mono text-xs text-muted mt-1">
                        {ev.event_date} {ev.event_time} • {ev.duration_min} min • Meeting #{ev.meeting_id}
                      </p>
                    </div>
                    <a href={icsDownloadUrl(ev.id)}
                      className="font-mono text-xs border border-border px-3 py-1 hover:border-accent hover:text-accent transition-colors">
                      .ics
                    </a>
                  </div>
                ))}
              </div>
            )
          }
        </main>
      </div>
    </>
  )
}
