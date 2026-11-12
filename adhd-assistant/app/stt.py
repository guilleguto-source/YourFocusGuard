from faster_whisper import WhisperModel


class STT:
    def __init__(self, model_size: str = "tiny"):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: str) -> str:
        segments, _ = self.model.transcribe(
            audio_path, language="es", beam_size=1, vad_filter=True
        )
        text = " ".join([seg.text for seg in segments])
        return text.strip()