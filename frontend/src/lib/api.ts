import axios from "axios"

const getBaseURL = () => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`
  }
  return "http://localhost:8000"
}

const api = axios.create({ baseURL: getBaseURL() })

export async function uploadAudio(file: File, numSpeakers?: number) {
  const form = new FormData()
  form.append("file", file)
  if (numSpeakers) form.append("num_speakers", String(numSpeakers))
  const { data } = await api.post("/upload/audio", form)
  return data
}

export async function getMeetingStatus(id: number) {
  const { data } = await api.get(`/meetings/${id}/status`)
  return data
}

export async function getMeeting(id: number) {
  const { data } = await api.get(`/meetings/${id}`)
  return data
}

export async function listMeetings() {
  const { data } = await api.get("/meetings/")
  return data
}

export async function getTasks(owner?: string, status?: string) {
  const { data } = await api.get("/tasks/", { params: { owner, status } })
  return data
}

export async function updateTask(id: number, status: string) {
  const { data } = await api.patch(`/tasks/${id}`, { status })
  return data
}

export async function search(query: string) {
  const { data } = await api.get("/search/", { params: { q: query } })
  return data
}

export async function getAnalytics() {
  const { data } = await api.get("/analytics/overview")
  return data
}

export async function getDailyReport() {
  const { data } = await api.get("/analytics/daily-report")
  return data
}

export async function getCalendarEvents(meetingId?: number) {
  const { data } = await api.get("/calendar/", { params: { meeting_id: meetingId } })
  return data
}

export const icsDownloadUrl = (eventId: number) => {
  const base = getBaseURL()
  return `${base}/calendar/${eventId}/download`
}

export async function startLiveMeeting(title: string) {
  const { data } = await api.post("/live/start", { title })
  return data
}

export async function queryLiveMeeting(meetingId: number, query: string) {
  const { data } = await api.post(`/live/${meetingId}/query`, { query })
  return data
}

export async function queryMemory(query: string) {
  const { data } = await api.get("/search/memory", { params: { q: query } })
  return data
}
