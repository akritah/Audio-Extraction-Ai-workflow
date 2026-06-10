import { useEffect, useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { getTasks, updateTask } from "@/lib/api"

const STATUSES = ["Pending", "In Progress", "Done", "Blocked"]

export default function TasksPage() {
  const [tasks,  setTasks]  = useState<any[]>([])
  const [filter, setFilter] = useState({ owner: "", status: "" })

  async function load() {
    const res = await getTasks(filter.owner || undefined, filter.status || undefined)
    setTasks(res)
  }

  useEffect(() => { load() }, [filter])

  async function cycle(task: any) {
    const idx  = STATUSES.indexOf(task.status)
    const next = STATUSES[(idx + 1) % STATUSES.length]
    await updateTask(task.id, next)
    load()
  }

  return (
    <>
      <Head><title>Tasks — Meeting Intelligence</title></Head>
      <div className="min-h-screen bg-paper">
        <header className="border-b border-border px-8 py-4 flex items-center gap-4">
          <Link href="/" className="font-mono text-sm text-muted hover:text-accent">← Dashboard</Link>
          <span className="font-serif text-xl">All Tasks</span>
        </header>

        <main className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <div className="flex gap-3">
            <input
              placeholder="Filter by owner"
              value={filter.owner}
              onChange={e => setFilter(f => ({ ...f, owner: e.target.value }))}
              className="border border-border px-3 py-2 text-sm font-mono bg-white focus:outline-none focus:border-accent w-40"
            />
            <select
              value={filter.status}
              onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
              className="border border-border px-3 py-2 text-sm font-mono bg-white focus:outline-none">
              <option value="">All statuses</option>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="border border-border bg-white divide-y divide-border">
            {tasks.length === 0
              ? <p className="p-5 text-sm text-muted">No tasks match.</p>
              : tasks.map((t: any) => (
                <div key={t.id} className="px-5 py-4 flex justify-between items-start gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-medium">{t.task}</p>
                    <p className="text-xs font-mono text-muted mt-1">
                      {t.owner || "Unassigned"} • {t.deadline || "No deadline"} • Meeting #{t.meeting_id}
                    </p>
                  </div>
                  <button
                    onClick={() => cycle(t)}
                    className={`text-xs font-mono px-2 py-1 border shrink-0 hover:bg-ink hover:text-paper transition-colors
                      ${t.status === "Done"
                        ? "border-green-400 text-green-700"
                        : t.status === "Blocked"
                        ? "border-red-400 text-red-700"
                        : "border-border text-muted"}`}>
                    {t.status}
                  </button>
                </div>
              ))
            }
          </div>
        </main>
      </div>
    </>
  )
}
