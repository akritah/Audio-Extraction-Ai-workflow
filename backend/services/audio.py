import os
import numpy as np

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "temp_audio")
os.makedirs(TEMP_DIR, exist_ok=True)


def load_and_clean(file_path: str) -> str:
    """
    Load audio, reduce background noise, normalize volume,
    and save a cleaned version. Returns path to the cleaned file.
    """
    import librosa
    import soundfile as sf
    import noisereduce as nr

    y, sr = librosa.load(file_path, sr=16000, mono=True)

    # noise reduction — first 0.5 seconds assumed to be ambient noise
    noise_sample = y[:int(sr * 0.5)]
    y_clean = nr.reduce_noise(y=y, sr=sr, y_noise=noise_sample, prop_decrease=0.75)

    # normalize to -1..1 range
    peak = np.abs(y_clean).max()
    if peak > 0:
        y_clean = y_clean / peak * 0.95

    base = os.path.splitext(os.path.basename(file_path))[0]
    out_path = os.path.join(TEMP_DIR, f"{base}_clean.wav")
    sf.write(out_path, y_clean, sr)

    return out_path


def split_into_chunks(file_path: str, chunk_sec: int = 300) -> list:
    """
    Split long recordings into smaller segments.
    Helps if diarization or transcription hits memory limits.
    Returns list of file paths.
    """
    import librosa
    import soundfile as sf

    y, sr = librosa.load(file_path, sr=16000, mono=True)
    total_samples = len(y)
    chunk_samples = chunk_sec * sr
    chunks = []

    for i, start in enumerate(range(0, total_samples, chunk_samples)):
        segment = y[start:start + chunk_samples]
        base = os.path.splitext(os.path.basename(file_path))[0]
        chunk_path = os.path.join(TEMP_DIR, f"{base}_chunk{i}.wav")
        sf.write(chunk_path, segment, sr)
        chunks.append(chunk_path)

    return chunks
