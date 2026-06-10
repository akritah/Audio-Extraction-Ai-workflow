import { useState, useRef } from "react"
import { useRouter } from "next/router"
import { uploadAudio } from "@/lib/api"

export default function UploadZone({ onDone }: { onDone?: () => void }) {
  const [dragging,    setDragging]    = useState(false)
  const [uploading,   setUploading]   = useState(false)
  const [numSpeakers, setNumSpeakers] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)
  const router   = useRouter()

  async function handle(file: File) {
    if (!file) return
    setUploading(true)
    try {
      const ns  = numSpeakers ? parseInt(numSpeakers) : undefined
      const res = await uploadAudio(file, ns)
      onDone?.()
      router.push(`/meetings/${res.meeting_id}`)
    } catch (e) {
      alert("Upload failed — is the backend running?")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={e  => { e.preventDefault(); setDragging(true)  }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault()
          setDragging(false)
          const f = e.dataTransfer.files[0]
          if (f) handle(f)
        }}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed p-10 text-center cursor-pointer transition-colors
          ${dragging ? "border-accent bg-accent/5" : "border-border hover:border-muted"}`}
      >
        <input
          ref={inputRef} type="file"
          accept=".wav,.mp3,.m4a,.ogg,.flac"
          className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) handle(f) }}
        />
        {uploading
          ? <p className="font-mono text-muted animate-pulse">Uploading…</p>
          : (
            <>
              <p className="font-mono text-sm text-muted">Drop audio file here or click to browse</p>
              <p className="text-xs text-muted/60 mt-1">.wav · .mp3 · .m4a · .ogg · .flac</p>
            </>
          )
        }
      </div>

      <div className="flex items-center gap-3">
        <label className="text-sm text-muted font-mono">Known speakers (optional):</label>
        <input
          type="number" min={1} max={20}
          value={numSpeakers}
          onChange={e => setNumSpeakers(e.target.value)}
          placeholder="auto"
          className="border border-border px-3 py-1 w-24 font-mono text-sm bg-white focus:outline-none focus:border-accent"
        />
      </div>
    </div>
  )
}
