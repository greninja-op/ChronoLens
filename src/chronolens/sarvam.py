"""Sarvam AI Multilingual Layer (Translation & Speech Synthesis).

Provides translation between English (en-IN) and Hindi (hi-IN) / Indian languages
for ChronoLens incident summaries, WhatsApp approval cards, and CFO ROI reports,
with graceful fallback if Sarvam is unconfigured.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Config

logger = logging.getLogger("chronolens.sarvam")

SARVAM_BASE_URL = "https://api.sarvam.ai"


def translate_text(
    text: str,
    target_lang: str = "hi-IN",
    source_lang: str = "en-IN",
    cfg: Config | None = None,
) -> str:
    """Translate text to target language (e.g., Hindi 'hi-IN') via Sarvam AI API."""
    if not text or not text.strip():
        return text

    cfg = cfg or Config.load()
    if not cfg.sarvam_enabled():
        return text  # Return original if Sarvam not configured

    url = f"{SARVAM_BASE_URL}/translate"
    headers = {
        "api-subscription-key": cfg.sarvam_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "input": text[:1000],
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "numerals_format": "international",
        "mode": "formal",
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=8.0)
        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("translated_text")
            if translated and isinstance(translated, str) and translated.strip():
                return translated.strip()
    except Exception as e:
        logger.warning(f"Sarvam translation failed: {e}")

    return text  # Safe fallback to original text


def text_to_speech(
    text: str,
    target_lang: str = "hi-IN",
    cfg: Config | None = None,
) -> dict[str, Any]:
    """Generate audio TTS speech from text via Sarvam Bulbul model."""
    cfg = cfg or Config.load()
    if not cfg.sarvam_enabled():
        return {"ok": False, "error": "Sarvam AI not enabled"}

    url = f"{SARVAM_BASE_URL}/text-to-speech"
    headers = {
        "api-subscription-key": cfg.sarvam_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:500],
        "target_language_code": target_lang,
        "speaker": cfg.sarvam_tts_speaker or "ritu",
        "model": cfg.sarvam_tts_model or "bulbul:v3",
        "output_audio_codec": "mp3",
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            audios = data.get("audios", [])
            if audios and isinstance(audios, list):
                return {"ok": True, "audio_b64": audios[0]}
        return {"ok": False, "status_code": resp.status_code, "body": resp.text}
    except Exception as e:
        logger.warning(f"Sarvam TTS failed: {e}")
        return {"ok": False, "error": str(e)}


def transcribe_speech(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    cfg: Config | None = None,
) -> dict[str, Any]:
    """Transcribe inbound WhatsApp voice notes via Sarvam Saaras STT model."""
    cfg = cfg or Config.load()
    if not cfg.sarvam_enabled() or not audio_bytes:
        return {"ok": False, "error": "Sarvam AI not enabled or empty audio"}

    url = f"{SARVAM_BASE_URL}/speech-to-text"
    headers = {
        "api-subscription-key": cfg.sarvam_api_key,
    }
    files = {
        "file": ("voice_note.ogg", audio_bytes, mime_type),
    }
    data = {
        "model": cfg.sarvam_stt_model or "saaras:v3",
        "language_code": "unknown",
    }

    try:
        resp = httpx.post(url, data=data, files=files, headers=headers, timeout=15.0)
        if resp.status_code == 200:
            res_json = resp.json()
            transcript = res_json.get("transcript", "")
            return {"ok": True, "transcript": transcript, "language": res_json.get("language_code")}
        return {"ok": False, "status_code": resp.status_code, "body": resp.text}
    except Exception as e:
        logger.warning(f"Sarvam STT failed: {e}")
        return {"ok": False, "error": str(e)}

