import os

# Use "medium" for a reasonable speed/accuracy tradeoff on CPU.
# Switch to "large-v3" if a GPU is available for significantly better accuracy.
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "medium")
DEVICE     = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE    = "int8" if DEVICE == "cpu" else "float16"

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
    return _model


import math
import logging
import librosa
import soundfile as sf

logger = logging.getLogger("uvicorn")

def ensure_mono_16khz(audio_path: str) -> str:
    """
    Checks if the audio file is mono 16kHz. If not, resamples and saves
    it to a temporary WAV file, returning the path to the resampled file.
    """
    try:
        info = sf.info(audio_path)
        if info.samplerate == 16000 and info.channels == 1:
            # Already mono 16kHz, return path directly
            return audio_path
    except Exception as e:
        logger.warning(f"[Whisper] Could not read audio info for {audio_path}: {e}")

    # Needs resampling
    logger.info(f"[Whisper] Resampling {audio_path} to mono 16kHz...")
    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        # Write to a temp file in the same directory
        base_dir = os.path.dirname(audio_path)
        temp_dir = os.path.join(base_dir, "temp_resampled")
        os.makedirs(temp_dir, exist_ok=True)
        base_name = os.path.basename(audio_path)
        resampled_path = os.path.join(temp_dir, f"resampled_16k_{base_name}")
        sf.write(resampled_path, y, 16000)
        return resampled_path
    except Exception as e:
        logger.error(f"[Whisper] Resampling failed for {audio_path}: {e}")
        return audio_path

def transcribe(audio_path: str, language: str = "en") -> list:
    """
    Run Whisper on the cleaned audio.
    Resamples to mono 16kHz before processing.
    Returns a list of segment dicts: {start, end, text, confidence}
    """
    model = get_model()

    # Ensure all audio is resampled to mono 16kHz, and get file path
    processed_path = ensure_mono_16khz(audio_path)

    # beam_size=5 gives better accuracy than the default greedy decode
    segments, info = model.transcribe(
        processed_path,
        language=language,
        beam_size=5,
        vad_filter=True,           # built-in silence filter
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,      # needed for accurate speaker alignment later
    )

    logger.info(
        f"[Whisper] Detected language: '{info.language}' "
        f"with confidence/probability: {info.language_probability:.4f}"
    )

    result = []
    for seg in segments:
        # avg_logprob is average log probability of the tokens. exp(avg_logprob) gets the confidence [0..1]
        confidence = math.exp(seg.avg_logprob)
        confidence = max(0.0, min(1.0, confidence)) # clamp to [0.0, 1.0]
        
        result.append({
            "start": round(seg.start, 2),
            "end":   round(seg.end, 2),
            "text":  seg.text.strip(),
            "confidence": round(confidence, 4)
        })

    # Clean up resampled file if it was created as a temp file
    if processed_path != audio_path and os.path.exists(processed_path):
        try:
            os.remove(processed_path)
        except Exception as cleanup_err:
            logger.warning(f"[Whisper] Failed to clean up resampled temp file: {cleanup_err}")

    return result


def segments_to_text(segments: list) -> str:
    return " ".join(s["text"] for s in segments)
