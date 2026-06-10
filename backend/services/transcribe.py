import os
from faster_whisper import WhisperModel

# Use "medium" for a reasonable speed/accuracy tradeoff on CPU.
# Switch to "large-v3" if a GPU is available for significantly better accuracy.
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "medium")
DEVICE     = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE    = "int8" if DEVICE == "cpu" else "float16"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
    return _model


def transcribe(audio_path: str, language: str = "en") -> list:
    """
    Run Whisper on the cleaned audio.
    Returns a list of segment dicts: {start, end, text}
    """
    model = get_model()

    # beam_size=5 gives better accuracy than the default greedy decode
    segments, _ = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,           # built-in silence filter
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,      # needed for accurate speaker alignment later
    )

    result = []
    for seg in segments:
        result.append({
            "start": round(seg.start, 2),
            "end":   round(seg.end, 2),
            "text":  seg.text.strip(),
        })

    return result


def segments_to_text(segments: list) -> str:
    return " ".join(s["text"] for s in segments)
