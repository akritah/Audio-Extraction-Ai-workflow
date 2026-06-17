import os
import re
import json
import numpy as np
from llm_client import ask_llm

# We can cache the model locally to make sure it runs offline
_classifier = None
_load_failed = False

def get_wav2vec2_classifier():
    global _classifier, _load_failed
    if _load_failed:
        return None
    if _classifier is None:
        try:
            from transformers import pipeline
            # Use a fast, standard speech emotion recognition model
            _classifier = pipeline(
                "audio-classification", 
                model="superb/wav2vec2-base-superb-er",
                device=-1 # Use CPU by default to keep VRAM free for LLM/PyAnnote
            )
        except Exception as e:
            print(f"[Emotion Service] Could not load Wav2Vec2 model: {e}. Using acoustic fallback.")
            _load_failed = True
    return _classifier

def detect_emotion_wav2vec2(audio_path: str) -> dict:
    """
    Attempt to run the superb/wav2vec2-base-superb-er pipeline.
    Map output classes to our standardized set of emotions.
    """
    classifier = get_wav2vec2_classifier()
    if classifier is None:
        raise RuntimeError("Wav2Vec2 model not available")

    # Load and resample to 16kHz mono before Whisper or emotion processing
    import librosa
    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        outputs = classifier({"raw": y, "sampling_rate": 16000})
    except Exception as e:
        print(f"[Emotion Service] Wav2Vec2 inference error: {e}")
        raise e
    
    # Example outputs: [{'label': 'neu', 'score': 0.85}, {'label': 'ang', 'score': 0.05}, ...]
    # Standard classes for superb-er: neu (neutral), hap (happy), sad (sad), ang (angry)
    mapping = {
        "neu": "Neutral",
        "hap": "Excited",
        "sad": "Worried",
        "ang": "Angry",
        "oth": "Neutral"
    }

    if outputs and len(outputs) > 0:
        top = outputs[0]
        label = top["label"].lower()
        mapped_label = mapping.get(label, "Neutral")
        return {
            "emotion": mapped_label,
            "confidence": round(top["score"], 2),
            "source": "Wav2Vec2"
        }
    return {"emotion": "Neutral", "confidence": 1.0, "source": "Wav2Vec2-Fallback"}
def detect_emotion_acoustic(audio_path: str, transcript_text: str) -> dict:
    """
    Offline-safe fallback using Librosa feature engineering:
    - Pitch (mean frequency of vocal tract vibration)
    - Energy (root-mean-square amplitude, i.e., volume)
    - ZCR (Zero-Crossing Rate, correlates with high arousal/unvoiced speech)
    - Silence ratio (pause tracking)
    - Speaking rate (words per second)
    """
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        if duration <= 0:
            return {"emotion": "Neutral", "confidence": 1.0, "source": "Acoustic-Fallback"}

        # 1. Energy (RMS)
        rms = librosa.feature.rms(y=y)
        energy_mean = float(np.mean(rms))

        # 2. Pitch
        try:
            pitches = librosa.yin(y, fmin=80, fmax=400)
            pitches = pitches[~np.isnan(pitches)]
            pitch_mean = float(np.mean(pitches)) if len(pitches) > 0 else 150.0
        except Exception:
            pitch_mean = 150.0

        # 3. ZCR (Zero Crossing Rate)
        zcr = librosa.feature.zero_crossing_rate(y=y)
        zcr_mean = float(np.mean(zcr))

        # 4. Speaking Rate
        words = len(transcript_text.split())
        speaking_rate = words / duration if duration > 0 else 0

        # 5. Pause ratio (silent frames < -35dB)
        db = librosa.amplitude_to_db(rms, ref=np.max)
        pause_ratio = float(np.mean(db < -35))

        # Rule-based heuristics
        # Standardize features: High/Low relative to baseline
        # Baseline rough estimates: energy_mean=0.03, pitch_mean=160Hz, speaking_rate=2.5 wps
        is_high_energy = energy_mean > 0.06
        is_high_pitch = pitch_mean > 200.0
        is_fast_speaking = speaking_rate > 3.5
        is_slow_speaking = speaking_rate < 1.2 and speaking_rate > 0
        is_hesitant = pause_ratio > 0.4

        if is_high_energy and is_high_pitch:
            emotion = "Angry" if is_fast_speaking else "Excited"
            confidence = 0.8
        elif is_hesitant or is_slow_speaking:
            emotion = "Worried" if is_high_pitch else "Hesitant"
            confidence = 0.7
        elif is_high_energy and not is_high_pitch:
            emotion = "Confident"
            confidence = 0.75
        else:
            emotion = "Neutral"
            confidence = 0.9

        return {
            "emotion": emotion,
            "confidence": confidence,
            "source": "Acoustic Heuristics"
        }
    except Exception as e:
        print(f"[Emotion Service] Heuristics failed: {e}")
        return {"emotion": "Neutral", "confidence": 1.0, "source": "Acoustic-Failure-Fallback"}

def detect_emotion(audio_path: str, transcript_text: str = "") -> dict:
    """
    Standard entrypoint for audio emotion analysis.
    Tries Wav2Vec2 pipeline first, then falls back to Librosa heuristics.
    """
    if not os.path.exists(audio_path):
        return {"emotion": "Neutral", "confidence": 1.0, "source": "Missing-File-Fallback"}
        
    try:
        return detect_emotion_wav2vec2(audio_path)
    except Exception:
        return detect_emotion_acoustic(audio_path, transcript_text)

def detect_context_emotion(transcript_text: str, audio_emotion: str, audio_confidence: float) -> dict:
    """
    Context-aware emotion detection that uses the local LLM to combine
    audio cues with semantic transcript content.
    """
    if not transcript_text or len(transcript_text.strip().split()) < 8:
        return {
            "emotion": audio_emotion,
            "confidence": audio_confidence,
            "explanation": "Segment text too short for semantic analysis. Relied on acoustic cues."
        }

    prompt = f"""You are analyzing a speaker's emotional state in a meeting.
Combine the transcript text and the audio pitch/volume tone (acoustic emotion) to determine the speaker's true feeling.

Transcript segment: "{transcript_text}"
Acoustic tone detected: {audio_emotion} (Confidence: {audio_confidence})

Evaluate the speaker's state. Be sensitive to frustration, anxiety, confidence, and excitement.
Choose exactly one of these:
- Angry
- Frustrated
- Excited
- Confident
- Worried
- Uncertain
- Hesitant
- Neutral

Return ONLY a valid JSON object. Do not include markdown tags, explanation text, or extra characters.
Example:
{{
  "emotion": "Frustrated",
  "confidence": 0.85,
  "explanation": "The speaker expresses disappointment with missed deadlines, reinforcing a frustrated tone."
}}
"""
    try:
        raw = ask_llm(prompt)
        raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        data = json.loads(raw)
        
        # Ensure returned emotion is one of the valid ones
        valid_emotions = {"Angry", "Frustrated", "Excited", "Confident", "Worried", "Uncertain", "Hesitant", "Neutral"}
        if data.get("emotion") in valid_emotions:
            try:
                conf_val = float(data.get("confidence", audio_confidence))
                conf_val = max(0.0, min(1.0, conf_val))
            except Exception:
                conf_val = audio_confidence

            return {
                "emotion": data["emotion"],
                "confidence": round(conf_val, 4),
                "explanation": data.get("explanation", "Resolved by LLM context reasoning.")
            }
    except Exception as e:
        print(f"[Emotion Service] Context emotion LLM failed: {e}")
        
    return {
        "emotion": audio_emotion,
        "confidence": audio_confidence,
        "explanation": f"Acoustic tone classified as {audio_emotion}. Semantic context reasoning failed/omitted."
    }
