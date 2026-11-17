import asyncio
import io
import logging
import subprocess
import wave
from typing import List

import numpy as np
import opuslib
from faster_whisper import WhisperModel
from piper import PiperVoice

from app.config import Settings

logger = logging.getLogger("stackchan.audio")


class AudioPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.whisper: WhisperModel | None = None
        self.voice: PiperVoice | None = None
        self._whisper_lock = asyncio.Lock()
        self._piper_lock = asyncio.Lock()

    def load_models(self) -> None:
        logger.info(
            "Loading Whisper model '%s' from %s",
            self.settings.whisper_model,
            self.settings.whisper_model_dir,
        )
        self.whisper = WhisperModel(
            self.settings.whisper_model,
            device="cpu",
            compute_type="int8",
            download_root=self.settings.whisper_model_dir,
        )
        logger.info("Loading Piper voice from %s", self.settings.piper_model_path)
        self.voice = PiperVoice.load(self.settings.piper_model_path)
        logger.info("Audio STT/TTS models ready")

    def opus_frames_to_pcm16(self, frames: List[bytes], sample_rate: int = 16000) -> bytes:
        if not frames:
            return b""
        decoder = opuslib.Decoder(sample_rate, 1)
        # Allow up to 120ms per packet when decoding
        max_frame_samples = int(sample_rate * 0.12)
        pcm_chunks: List[bytes] = []
        for pkt in frames:
            if not pkt:
                continue
            try:
                pcm = decoder.decode(pkt, max_frame_samples)
                if pcm:
                    pcm_chunks.append(pcm)
            except Exception as exc:
                logger.debug("Skipped bad Opus packet (%d bytes): %s", len(pkt), exc)
        return b"".join(pcm_chunks)

    def opus_frames_to_wav(self, frames: List[bytes], sample_rate: int = 16000) -> bytes:
        pcm = self.opus_frames_to_pcm16(frames, sample_rate=sample_rate)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()

    def _transcribe_pcm16_sync(self, pcm: bytes, sample_rate: int = 16000) -> str:
        if not self.whisper:
            raise RuntimeError("Whisper model not loaded")
        if len(pcm) < sample_rate // 5 * 2:  # < 0.2s audio
            return ""

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate != 16000:
            # Resample cleanly via ffmpeg if needed
            wav_in = io.BytesIO()
            with wave.open(wav_in, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm)
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "wav",
                    "-i",
                    "pipe:0",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "s16le",
                    "pipe:1",
                ],
                input=wav_in.getvalue(),
                capture_output=True,
                check=True,
                timeout=30,
            )
            audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _info = self.whisper.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
        return text

    async def transcribe_opus_frames(self, frames: List[bytes], sample_rate: int = 16000) -> str:
        pcm = await asyncio.to_thread(self.opus_frames_to_pcm16, frames, sample_rate)
        if not pcm:
            return ""
        async with self._whisper_lock:
            return await asyncio.to_thread(self._transcribe_pcm16_sync, pcm, sample_rate)

    def _synthesize_wav_sync(self, text: str) -> bytes:
        if not self.voice:
            raise RuntimeError("Piper voice not loaded")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if hasattr(self.voice, "synthesize_wav"):
                self.voice.synthesize_wav(text, wf)
            else:
                self.voice.synthesize(text, wf)
        return buf.getvalue()

    def _wav_to_pcm16_resampled(self, wav_bytes: bytes, sample_rate: int = 24000) -> bytes:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "wav",
                "-i",
                "pipe:0",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=wav_bytes,
            capture_output=True,
            check=True,
            timeout=30,
        )
        return proc.stdout

    def _text_to_opus_frames_sync(
        self,
        text: str,
        sample_rate: int = 24000,
        frame_duration_ms: int = 60,
    ) -> List[bytes]:
        if not text.strip():
            return []
        wav_bytes = self._synthesize_wav_sync(text)
        pcm = self._wav_to_pcm16_resampled(wav_bytes, sample_rate=sample_rate)
        if not pcm:
            return []

        frame_samples = (sample_rate * frame_duration_ms) // 1000
        frame_bytes = frame_samples * 2  # 16-bit mono
        encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_VOIP)

        frames: List[bytes] = []
        for offset in range(0, len(pcm), frame_bytes):
            chunk = pcm[offset : offset + frame_bytes]
            if len(chunk) < frame_bytes:
                chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
            encoded = encoder.encode(chunk, frame_samples)
            frames.append(bytes(encoded))
        return frames

    async def text_to_opus_frames(
        self,
        text: str,
        sample_rate: int = 24000,
        frame_duration_ms: int = 60,
    ) -> List[bytes]:
        async with self._piper_lock:
            return await asyncio.to_thread(
                self._text_to_opus_frames_sync,
                text,
                sample_rate,
                frame_duration_ms,
            )
