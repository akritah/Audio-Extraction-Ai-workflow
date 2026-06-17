import { useEffect, useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { getAnalytics, getDailyReport, listMeetings } from "@/lib/api"
import UploadZone from "@/components/UploadZone"

export default function Home() {
  const [stats,   setStats]   = useState<any>(null)
  const [report,  setReport]  = useState<any>(null)
  const [meetings, setMeetings] = useState<any[]>([])

  useEffect(() => {
    getAnalytics().then(setStats).catch(console.error)
    getDailyReport().then(setReport).catch(console.error)
    listMeetings().then(setMeetings).catch(console.error)
  }, [])

  return (
    <>
      <Head>
        <title>Meeting Intelligence</title>
      </Head>

      <div className="min-h-screen bg-paper">
        {/* top bar */}
        <header className="border-b border-border px-8 py-4 flex items-center justify-between">
          <span className="font-serif text-2xl text-ink">Meeting Intelligence</span>
          <nav className="flex gap-6 text-sm font-mono text-muted">
            <Link href="/"        className="hover:text-accent">Dashboard</Link>
            <Link href="/live"    className="hover:text-accent text-indigo-600 font-semibold">Real-Time Meeting</Link>
            <Link href="/tasks"   className="hover:text-accent">Tasks</Link>
            <Link href="/search"  className="hover:text-accent">Search</Link>
            <Link href="/calendar" className="hover:text-accent">Calendar</Link>
          </nav>
        </header>

        <main className="max-w-6xl mx-auto px-8 py-10 space-y-10">

          {/* upload */}
          <section>
            <h2 className="font-serif text-xl mb-4">Upload Recording</h2>
            <UploadZone onDone={() => listMeetings().then(setMeetings)} />
          </section>

          {/* stats row */}
          {stats && (
            <section>
              <h2 className="font-serif text-xl mb-4">Overview</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Meetings",        value: stats.total_meetings  },
                  { label: "Total Tasks",     value: stats.total_tasks     },
                  { label: "Pending",         value: stats.pending_tasks   },
                  { label: "Calendar Events", value: stats.total_events    },
                ].map(s => (
                  <div key={s.label} className="border border-border p-5 bg-white">
                    <div className="font-mono text-3xl text-accent">{s.value ?? "—"}</div>
                    <div className="text-sm text-muted mt-1">{s.label}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* tasks by person */}
          {stats?.tasks_per_person?.length > 0 && (
            <section>
              <h2 className="font-serif text-xl mb-4">Tasks by Person</h2>
              <div className="border border-border bg-white divide-y divide-border">
                {stats.tasks_per_person.map((row: any) => (
                  <div key={row.owner} className="flex items-center justify-between px-5 py-3">
                    <span className="font-medium">{row.owner || "Unassigned"}</span>
                    <span className="font-mono text-accent">{row.count}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* daily report */}
          {report && (
            <section>
              <h2 className="font-serif text-xl mb-4">
                Daily Report — <span className="font-mono text-muted text-base">{report.date}</span>
              </h2>
              {report.overdue?.length > 0 && (
                <div className="mb-4 border border-accent/40 bg-accent/5 p-4">
                  <p className="font-medium text-accent mb-2">Overdue ({report.overdue.length})</p>
                  {report.overdue.map((t: any, i: number) => (
                    <p key={i} className="text-sm text-muted font-mono">
                      {t.task} — {t.owner} — was due {t.deadline}
                    </p>
                  ))}
                </div>
              )}
              {report.upcoming?.length > 0 && (
                <div className="border border-border bg-white p-4">
                  <p className="font-medium mb-2">Upcoming Meetings</p>
                  {report.upcoming.map((e: any, i: number) => (
                    <p key={i} className="text-sm text-muted font-mono">
                      {e.title} — {e.event_date} {e.event_time}
                    </p>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* recent meetings */}
          <section>
            <h2 className="font-serif text-xl mb-4">Recent Meetings</h2>
            {meetings.length === 0
              ? <p className="text-muted text-sm">No meetings processed yet.</p>
              : (
                <div className="border border-border bg-white divide-y divide-border">
                  {meetings.map((m: any) => (
                    <Link key={m.id} href={`/meetings/${m.id}`}
                      className="flex justify-between items-center px-5 py-4 hover:bg-paper transition-colors">
                      <span className="font-medium">{m.filename}</span>
                      <span className="font-mono text-sm text-muted">{m.created_at?.slice(0, 10)}</span>
                    </Link>
                  ))}
                </div>
              )
            }
          </section>
        </main>
      </div>
    </>
  )
}
