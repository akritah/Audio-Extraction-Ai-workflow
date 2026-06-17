import { useEffect, useRef, useState } from "react"
import Head from "next/head"
import Link from "next/link"
import { startLiveMeeting, queryLiveMeeting, queryMemory } from "@/lib/api"

function resample(inputBuffer: Float32Array, fromSampleRate: number, toSampleRate: number): Float32Array {
  if (fromSampleRate === toSampleRate) {
    return inputBuffer
  }
  const ratio = fromSampleRate / toSampleRate
  const newLength = Math.round(inputBuffer.length / ratio)
  const result = new Float32Array(newLength)
  let offsetResult = 0
  let offsetInput = 0
  while (offsetResult < result.length) {
    const nextOffsetInput = Math.round((offsetResult + 1) * ratio)
    let accum = 0
    let count = 0
    for (let i = offsetInput; i < nextOffsetInput && i < inputBuffer.length; i++) {
      accum += inputBuffer[i]
      count++
    }
    result[offsetResult] = count > 0 ? accum / count : 0
    offsetResult++
    offsetInput = nextOffsetInput
  }
  return result
}

interface Segment {
  speaker: string
  start: number
  end: number
  text: string
  emotion: string
  explanation?: string
}

interface Task {
  task: string
  owner: string
  deadline: string
  status?: string
}

interface CalendarEvent {
  title: string
  date: string
  time: string
  participants: string[]
}

interface SentimentState {
  meeting_sentiment: string
  dominant_emotion: string
  confidence: number
  observations: string[]
}

export default function LiveMeeting() {
  const [meetingId, setMeetingId] = useState<number | null>(null)
  const [meetingTitle, setMeetingTitle] = useState("Live Meeting Session")
  const [isRecording, setIsRecording] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [errorMessage, setErrorMessage] = useState("")
  
  // Dashboard panels data
  const [transcript, setTranscript] = useState<Segment[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [summary, setSummary] = useState("")
  const [sentiment, setSentiment] = useState<SentimentState>({
    meeting_sentiment: "Neutral",
    dominant_emotion: "Neutral",
    confidence: 1.0,
    observations: ["No data collected yet."]
  })

  // Live Q&A state
  const [qaQuery, setQaQuery] = useState("")
  const [qaAnswer, setQaAnswer] = useState("")
  const [qaLoading, setQaLoading] = useState(false)

  // Memory query state (general queries)
  const [memQuery, setMemQuery] = useState("")
  const [memAnswer, setMemAnswer] = useState("")
  const [memLoading, setMemLoading] = useState(false)

  // Audio recording refs
  const streamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  
  const isMutedRef = useRef(false)
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  // Scroll to bottom of transcript
  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [transcript])

  // Sync mute state to ref
  useEffect(() => {
    isMutedRef.current = isMuted
  }, [isMuted])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecordingSession()
    }
  }, [])

  const startMeetingSession = async () => {
    if (isRecording) return
    console.log("[Live Portal] startMeetingSession invoked. Title:", meetingTitle)
    setErrorMessage("")
    try {
      // 1. Create meeting in SQLite
      console.log("[Live Portal] 1. Requesting backend to create live meeting...")
      const res = await startLiveMeeting(meetingTitle)
      const mId = res.meeting_id
      setMeetingId(mId)
      console.log("[Live Portal] SQLite meeting record created. ID:", mId)

      // Reset states
      setTranscript([])
      setTasks([])
      setEvents([])
      setSummary("")
      setSentiment({
        meeting_sentiment: "Neutral",
        dominant_emotion: "Neutral",
        confidence: 1.0,
        observations: ["Meeting initialized. Awaiting speaker audio..."]
      })
      setQaAnswer("")
      
      // 2. Request mic access and setup Web Audio API
      console.log("[Live Portal] 2. Requesting microphone access (navigator.mediaDevices.getUserMedia)...")
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      console.log("[Live Portal] Microphone access GRANTED. Stream acquired.")

      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
      console.log("[Live Portal] Initializing native AudioContext...")
      const audioCtx = new AudioCtx()
      audioContextRef.current = audioCtx
      console.log("[Live Portal] AudioContext initialized. Hardware sample rate:", audioCtx.sampleRate)

      if (audioCtx.state === "suspended") {
        console.log("[Live Portal] AudioContext is suspended. Resuming context...")
        await audioCtx.resume()
        console.log("[Live Portal] AudioContext state after resume:", audioCtx.state)
      }

      const source = audioCtx.createMediaStreamSource(stream)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      source.connect(processor)
      processor.connect(audioCtx.destination)
      console.log("[Live Portal] Web Audio node graph connected.")

      // 3. Connect WebSocket dynamically based on current browser host
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const socketUrl = `${protocol}//${window.location.hostname}:8000/live/ws/live/${mId}`
      console.log("[Live Portal] 3. Opening WebSocket connection to:", socketUrl)
      const ws = new WebSocket(socketUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log("[Live Portal] WebSocket handshake completed. Ready to stream.")
        setIsRecording(true)
        setIsMuted(false)
        setErrorMessage("")
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        console.log("[Live Portal] WebSocket message received:", data.type)
        if (data.type === "chunk_update") {
          setTranscript((prev) => [...prev, data.segment])
          if (data.new_tasks && data.new_tasks.length > 0) {
            setTasks((prev) => {
              const existing = new Set(prev.map(t => t.task.toLowerCase()))
              const filtered = data.new_tasks.filter((t: Task) => !existing.has(t.task.toLowerCase()))
              return [...prev, ...filtered]
            })
          }
          if (data.new_events && data.new_events.length > 0) {
            setEvents((prev) => {
              const existing = new Set(prev.map(e => e.title.toLowerCase()))
              const filtered = data.new_events.filter((e: CalendarEvent) => !existing.has(e.title.toLowerCase()))
              return [...prev, ...filtered]
            })
          }
        } else if (data.type === "intelligence_update") {
          setTranscript((prev) => 
            prev.map(seg => 
              seg.start === data.segment_start 
                ? { ...seg, emotion: data.emotion, explanation: data.explanation } 
                : seg
            )
          )
          if (data.new_tasks && data.new_tasks.length > 0) {
            setTasks((prev) => {
              const existing = new Set(prev.map(t => t.task.toLowerCase()))
              const filtered = data.new_tasks.filter((t: Task) => !existing.has(t.task.toLowerCase()))
              return [...prev, ...filtered]
            })
          }
          if (data.new_events && data.new_events.length > 0) {
            setEvents((prev) => {
              const existing = new Set(prev.map(e => e.title.toLowerCase()))
              const filtered = data.new_events.filter((e: CalendarEvent) => !existing.has(e.title.toLowerCase()))
              return [...prev, ...filtered]
            })
          }
        } else if (data.type === "diarization_update") {
          setTranscript(data.transcript)
        } else if (data.type === "summary_update") {
          setSummary(data.summary)
          if (data.sentiment) {
            setSentiment(data.sentiment)
          }
        }
      }

      ws.onerror = (err) => {
        console.error("[Live Portal] WebSocket onerror triggered:", err)
        setErrorMessage("WebSocket connection error. Verify backend server is running on port 8000.")
      }

      ws.onclose = (event) => {
        console.log("[Live Portal] WebSocket closed. code:", event.code, "wasClean:", event.wasClean)
        setIsRecording(false)
        if (!event.wasClean) {
          setErrorMessage(`WebSocket connection closed unexpectedly (code: ${event.code}).`)
        }
      }

      processor.onaudioprocess = (e) => {
        if (isMutedRef.current) return
        const inputData = e.inputBuffer.getChannelData(0)
        const resampled = resample(inputData, audioCtx.sampleRate, 16000)
        
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(resampled)
        }
      }

    } catch (err: any) {
      console.error("[Live Portal] startMeetingSession caught error:", err)
      setErrorMessage(err.message || String(err))
      alert(`Could not start meeting: ${err.message || String(err)}`)
    }
  }

  const stopRecordingSession = () => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsRecording(false)
  }

  const toggleMute = () => {
    setIsMuted((prev) => !prev)
  }

  const handleLiveQa = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!meetingId || !qaQuery.trim()) return
    setQaLoading(true)
    setQaAnswer("")
    try {
      const res = await queryLiveMeeting(meetingId, qaQuery)
      setQaAnswer(res.answer)
    } catch (err) {
      console.error("Live Q&A query failed:", err)
      setQaAnswer("Error getting answer from meeting context.")
    } finally {
      setQaLoading(false)
    }
  }

  const handleMemorySearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!memQuery.trim()) return
    setMemLoading(true)
    setMemAnswer("")
    try {
      const res = await queryMemory(memQuery)
      setMemAnswer(res.answer)
    } catch (err) {
      console.error("Memory query failed:", err)
      setMemAnswer("Failed to query persistent memory.")
    } finally {
      setMemLoading(false)
    }
  }

  const getEmotionEmoji = (emotion: string) => {
    const emo = emotion.toLowerCase()
    if (emo.includes("angry") || emo.includes("frustrated")) return "😡"
    if (emo.includes("excit") || emo.includes("happ")) return "🎉"
    if (emo.includes("confid") || emo.includes("assert")) return "💪"
    if (emo.includes("worr") || emo.includes("anxi")) return "😟"
    if (emo.includes("uncert") || emo.includes("hesit")) return "❓"
    return "💬"
  }

  const getEmotionBadgeColor = (emotion: string) => {
    const emo = emotion.toLowerCase()
    if (emo.includes("angry") || emo.includes("frustrated")) return "bg-red-50 text-red-700 border-red-200"
    if (emo.includes("excit") || emo.includes("happ")) return "bg-green-50 text-green-700 border-green-200"
    if (emo.includes("confid")) return "bg-blue-50 text-blue-700 border-blue-200"
    if (emo.includes("worr") || emo.includes("hesit")) return "bg-yellow-50 text-yellow-700 border-yellow-200"
    return "bg-slate-50 text-slate-700 border-slate-200"
  }

  const getSentimentBg = (sentiment: string) => {
    const sent = sentiment.toLowerCase()
    if (sent.includes("pos")) return "bg-emerald-50 border-emerald-200 text-emerald-800"
    if (sent.includes("neg")) return "bg-rose-50 border-rose-200 text-rose-800"
    return "bg-slate-50 border-slate-200 text-slate-800"
  }

  return (
    <>
      <Head>
        <title>Real-Time Meeting Intelligence Assistant</title>
      </Head>

      <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
        {/* Navigation Bar */}
        <header className="border-b border-slate-800 bg-slate-950 px-8 py-4 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${isRecording ? "bg-emerald-500 animate-pulse shadow-[0_0_8px_#10b981]" : "bg-red-500"}`} />
            <span className="font-semibold text-lg text-white">Live Intelligence Portal</span>
          </div>
          <nav className="flex gap-6 text-sm font-mono text-slate-400">
            <Link href="/" className="hover:text-white transition-colors">Dashboard</Link>
            <Link href="/live" className="text-white hover:text-white transition-colors font-semibold">Real-Time</Link>
            <Link href="/tasks" className="hover:text-white transition-colors">Tasks</Link>
            <Link href="/search" className="hover:text-white transition-colors">Search</Link>
          </nav>
        </header>

        {/* Content Body */}
        <main className="flex-1 p-6 md:p-8 space-y-6 max-w-7xl mx-auto w-full">
          {/* Error Banner */}
          {errorMessage && (
            <div className="bg-rose-500/20 border border-rose-500/40 text-rose-300 p-4 rounded-xl text-sm font-mono shadow-[0_0_12px_rgba(244,63,94,0.1)]">
              <strong>Error:</strong> {errorMessage}
            </div>
          )}
          {/* Controls Bar */}
          <section className="bg-slate-950/60 backdrop-blur-md border border-slate-800 p-5 rounded-2xl flex flex-col sm:flex-row gap-4 items-center justify-between shadow-md">
            <div className="flex flex-col gap-1 w-full sm:w-auto">
              <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Session Title</span>
              <input
                type="text"
                value={meetingTitle}
                onChange={(e) => setMeetingTitle(e.target.value)}
                disabled={isRecording}
                className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-sm font-medium w-full sm:w-64 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              />
            </div>
            
            <div className="flex gap-3 w-full sm:w-auto justify-end">
              {isRecording && (
                <button
                  onClick={toggleMute}
                  className={`px-4 py-2 rounded-xl border font-mono text-xs transition-all ${
                    isMuted
                      ? "bg-amber-600/20 border-amber-500/40 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.1)]"
                      : "bg-slate-900 border-slate-800 hover:border-slate-700 text-slate-300"
                  }`}
                >
                  {isMuted ? "🎤 UNMUTE" : "🔇 MUTE MIC"}
                </button>
              )}
              
              {!isRecording ? (
                <button
                  onClick={startMeetingSession}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm px-6 py-2.5 rounded-xl shadow-md shadow-indigo-600/20 hover:shadow-indigo-600/30 transition-all"
                >
                  Start Meeting
                </button>
              ) : (
                <button
                  onClick={stopRecordingSession}
                  className="bg-rose-600 hover:bg-rose-500 text-white font-semibold text-sm px-6 py-2.5 rounded-xl shadow-md shadow-rose-600/20 hover:shadow-rose-600/30 transition-all"
                >
                  Stop & Finalize
                </button>
              )}
            </div>
          </section>

          {/* Core Dashboard Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* LEFT COLUMN: Transcript & Live Q&A (7 cols) */}
            <div className="lg:col-span-7 space-y-6 flex flex-col h-[750px]">
              
              {/* Transcript Panel */}
              <div className="flex-1 bg-slate-950/40 border border-slate-800/80 rounded-2xl flex flex-col shadow-inner overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
                  <h3 className="font-semibold text-sm text-slate-200">Live Transcript</h3>
                  {isRecording && <span className="text-[10px] font-mono text-emerald-400 animate-pulse">Streaming 16kHz PCM...</span>}
                </div>
                
                <div className="flex-1 p-5 overflow-y-auto space-y-4 max-h-[420px]">
                  {transcript.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm">
                      <p className="font-mono text-xs">Waiting for speech...</p>
                    </div>
                  ) : (
                    transcript.map((seg, i) => (
                      <div key={i} className="flex gap-4 items-start group">
                        <div className="w-24 shrink-0 font-mono text-[11px] text-slate-400 pt-0.5">
                          <span className="font-semibold text-slate-200 block truncate">{seg.speaker}</span>
                          <span>{Math.floor(seg.start)}s - {Math.floor(seg.end)}s</span>
                        </div>
                        
                        <div className="flex-1 space-y-1 bg-slate-900/60 hover:bg-slate-900 border border-slate-800/60 p-3.5 rounded-xl transition-all">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm text-slate-100">{seg.text}</span>
                          </div>
                          {seg.emotion && (
                            <div className="pt-2 flex items-center gap-1.5">
                              <span className={`text-[10px] font-semibold font-mono border px-2 py-0.5 rounded-full flex items-center gap-1 ${getEmotionBadgeColor(seg.emotion)}`}>
                                <span>{getEmotionEmoji(seg.emotion)}</span>
                                <span>{seg.emotion}</span>
                              </span>
                              {seg.explanation && (
                                <span className="text-[10px] text-slate-400 italic truncate max-w-md" title={seg.explanation}>
                                  — {seg.explanation}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={transcriptEndRef} />
                </div>
              </div>

              {/* In-Meeting Live Q&A Panel */}
              <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl flex flex-col shadow-lg overflow-hidden shrink-0">
                <div className="px-5 py-3 border-b border-slate-800 bg-slate-950/60">
                  <h3 className="font-semibold text-sm text-indigo-400">Ask AI Questions from Active Audio</h3>
                </div>
                
                <form onSubmit={handleLiveQa} className="p-4 flex gap-3 border-b border-slate-800/60">
                  <input
                    type="text"
                    value={qaQuery}
                    onChange={(e) => setQaQuery(e.target.value)}
                    placeholder="Ask something (e.g., 'What was the timeline discussed?', 'What deadline did Priya get?')"
                    className="flex-1 bg-slate-900 border border-slate-850 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-indigo-500 placeholder-slate-500 text-slate-100"
                    disabled={!meetingId}
                  />
                  <button
                    type="submit"
                    className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white font-mono text-xs px-4 py-2 rounded-xl transition-all"
                    disabled={!meetingId || qaLoading}
                  >
                    {qaLoading ? "..." : "QUERY"}
                  </button>
                </form>

                <div className="p-4 bg-slate-950/20 text-sm min-h-[70px] max-h-[140px] overflow-y-auto">
                  {!meetingId ? (
                    <p className="text-slate-500 text-xs italic">Start a meeting to query active audio in real time.</p>
                  ) : qaLoading ? (
                    <p className="text-slate-400 text-xs animate-pulse">Consulting LLM and transcription logs...</p>
                  ) : qaAnswer ? (
                    <div className="space-y-1">
                      <p className="text-xs font-mono text-indigo-400">AI Response:</p>
                      <p className="text-slate-200 leading-relaxed font-sans">{qaAnswer}</p>
                    </div>
                  ) : (
                    <p className="text-slate-500 text-xs italic">Ask any question to trace real-time decisions, numbers, or assignments.</p>
                  )}
                </div>
              </div>

            </div>

            {/* RIGHT COLUMN: Summary, Tasks, Sentiment, Events (5 cols) */}
            <div className="lg:col-span-5 space-y-6 flex flex-col h-[750px] overflow-y-auto pr-1">
              
              {/* Running Atmosphere & Sentiment */}
              <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl p-5 shadow-lg space-y-4">
                <h3 className="font-semibold text-sm text-slate-200">Atmosphere Sentiment</h3>
                
                <div className="flex gap-4 items-center">
                  <div className={`px-4 py-2.5 rounded-xl border text-center ${getSentimentBg(sentiment.meeting_sentiment)}`}>
                    <div className="text-[10px] font-mono uppercase tracking-wider opacity-60">Sentiment</div>
                    <div className="text-lg font-bold">{sentiment.meeting_sentiment}</div>
                  </div>
                  
                  <div className="bg-slate-900 border border-slate-800 px-4 py-2.5 rounded-xl text-left flex-1">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Dominant Emotion</div>
                    <div className="text-base font-semibold text-slate-100 flex items-center gap-1.5">
                      <span>{getEmotionEmoji(sentiment.dominant_emotion)}</span>
                      <span>{sentiment.dominant_emotion}</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Tone Observations</span>
                  <div className="space-y-1.5">
                    {sentiment.observations.map((obs, index) => (
                      <p key={index} className="text-xs text-slate-300 font-mono flex items-start gap-2">
                        <span className="text-indigo-400">•</span>
                        <span>{obs}</span>
                      </p>
                    ))}
                  </div>
                </div>
              </div>

              {/* Running Summary */}
              <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl p-5 shadow-lg flex-1 flex flex-col min-h-[220px]">
                <h3 className="font-semibold text-sm text-slate-200 mb-3">Incremental Summary (30s Updates)</h3>
                <div className="flex-1 overflow-y-auto bg-slate-900/40 border border-slate-800/60 p-4 rounded-xl text-xs leading-relaxed text-slate-300 whitespace-pre-wrap font-serif">
                  {summary ? summary : "A running summary of discussion points, decisions, and outcomes will render here incrementally."}
                </div>
              </div>

              {/* Action Items Panel */}
              <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl p-5 shadow-lg min-h-[160px] flex flex-col">
                <h3 className="font-semibold text-sm text-slate-200 mb-3">Real-Time Action Items</h3>
                <div className="flex-1 overflow-y-auto space-y-2 max-h-[200px]">
                  {tasks.length === 0 ? (
                    <p className="text-slate-500 text-xs italic">No actions identified yet.</p>
                  ) : (
                    tasks.map((t, idx) => (
                      <div key={idx} className="flex justify-between items-start bg-slate-900/60 border border-slate-850 p-3 rounded-xl">
                        <div className="space-y-1">
                          <p className="text-xs font-medium text-slate-100">{t.task}</p>
                          <p className="text-[10px] font-mono text-slate-400">
                            Owner: <span className="text-slate-200">{t.owner || "Unassigned"}</span> • Due: <span className="text-slate-200">{t.deadline || "No deadline"}</span>
                          </p>
                        </div>
                        <span className="text-[9px] font-mono border border-indigo-500/40 text-indigo-300 px-2 py-0.5 rounded bg-indigo-500/5">
                          Pending
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Calendar & Upcoming events */}
              {events.length > 0 && (
                <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl p-5 shadow-lg">
                  <h3 className="font-semibold text-sm text-slate-200 mb-3">Detected Scheduled Events</h3>
                  <div className="space-y-2">
                    {events.map((ev, index) => (
                      <div key={index} className="bg-slate-900 border border-slate-850 p-3 rounded-xl flex justify-between items-center">
                        <div>
                          <p className="text-xs font-semibold text-slate-100">{ev.title}</p>
                          <p className="text-[10px] font-mono text-slate-400">{ev.date} at {ev.time}</p>
                        </div>
                        <span className="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded">
                          Scheduled
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          </div>

          {/* Historical Meeting Memory Query (Persistent) */}
          <section className="bg-slate-950/60 border border-slate-800 p-6 rounded-2xl shadow-xl space-y-4">
            <h3 className="font-semibold text-sm text-indigo-400">Search Overall Meeting Memory Assistant</h3>
            <p className="text-xs text-slate-400">Ask questions across ALL historical meetings (e.g. "What concerns were repeatedly raised by Rahul?", "Show meetings where timeline issues generated negative sentiment")</p>
            
            <form onSubmit={handleMemorySearch} className="flex gap-3">
              <input
                type="text"
                value={memQuery}
                onChange={(e) => setMemQuery(e.target.value)}
                placeholder="Query global meeting archive..."
                className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-indigo-500 placeholder-slate-500 text-slate-100"
              />
              <button
                type="submit"
                className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white font-mono text-xs px-5 py-2.5 rounded-xl transition-all"
                disabled={memLoading}
              >
                {memLoading ? "..." : "QUERY MEMORY"}
              </button>
            </form>

            <div className="bg-slate-900/60 border border-slate-850/80 p-4 rounded-xl min-h-[90px]">
              {memLoading ? (
                <div className="flex items-center gap-2 text-slate-400 text-xs animate-pulse">
                  <span>Searching sqlite structure and vector embeds...</span>
                </div>
              ) : memAnswer ? (
                <div className="space-y-1.5">
                  <p className="text-xs font-mono text-indigo-400">Memory Agent Response:</p>
                  <p className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap">{memAnswer}</p>
                </div>
              ) : (
                <p className="text-slate-500 text-xs italic">Memory answers will synthesize summaries, historical tasks, scheduling, and sentiment trends.</p>
              )}
            </div>
          </section>

        </main>
      </div>
    </>
  )
}
