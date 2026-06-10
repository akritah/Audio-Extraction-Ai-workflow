import os
from pyannote.audio import Pipeline

# Download model once: https://huggingface.co/pyannote/speaker-diarization-3.1
# Set HF_HOME to a local path so it stays offline after first pull
HF_TOKEN   = os.environ.get("HF_TOKEN", "")
MODEL_NAME = "pyannote/speaker-diarization-3.1"

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline.from_pretrained(MODEL_NAME, use_auth_token=HF_TOKEN)
    return _pipeline


def run_diarization(audio_path: str, num_speakers: int = None) -> list:
    """
    Returns a list of {speaker, start, end} segments.
    Passing num_speakers locks the count and avoids over-segmentation.
    """
    pipe = get_pipeline()

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers

    diarization = pipe(audio_path, **kwargs)

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "speaker": speaker,
            "start":   round(turn.start, 2),
            "end":     round(turn.end, 2),
        })

    return segments


def align_transcript_with_speakers(transcript_segs: list, diarization_segs: list) -> list:
    """
    Match each transcription segment to the speaker who was talking
    at the midpoint of that segment. Simple overlap heuristic — fast enough
    for meetings under an hour.
    """
    result = []

    for t in transcript_segs:
        midpoint = (t["start"] + t["end"]) / 2
        speaker  = "Unknown"

        for d in diarization_segs:
            if d["start"] <= midpoint <= d["end"]:
                speaker = d["speaker"]
                break

        result.append({
            "speaker": speaker,
            "start":   t["start"],
            "end":     t["end"],
            "text":    t["text"],
        })

    return result
