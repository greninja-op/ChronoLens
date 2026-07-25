"""Unit & Property-based tests for Sarvam AI Multilingual Layer (Translation, STT, TTS) in ChronoLens:

- Text Translation (en-IN <-> hi-IN)
- Speech-to-Text (Sarvam Saaras v3)
- Text-to-Speech (Sarvam Bulbul v3)
- WhatsApp Multilingual Approval Cards
"""
from __future__ import annotations

import os
import sys
from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chronolens.config import Config
from chronolens.foresee import Forecast
from chronolens.sarvam import text_to_speech, transcribe_speech, translate_text
from chronolens.whatsapp_bot import post_whatsapp_approval


def test_sarvam_translation_fallback():
    cfg = Config.load()
    # Test safe fallback
    result = translate_text("System latency is rising", target_lang="hi-IN", cfg=cfg)
    assert isinstance(result, str)
    assert len(result) > 0


@settings(deadline=None)
@given(text=st.text(min_size=1, max_size=100))
def test_sarvam_translation_property(text: str):
    cfg = Config.load()
    res = translate_text(text, target_lang="hi-IN", cfg=cfg)
    assert isinstance(res, str)



def test_sarvam_tts_structure():
    cfg = Config.load()
    res = text_to_speech("Warning: checkout service p99 rising", target_lang="hi-IN", cfg=cfg)
    assert isinstance(res, dict)
    assert "ok" in res


def test_sarvam_stt_structure():
    cfg = Config.load()
    res = transcribe_speech(b"OggOpusDummyHeaderBytes", mime_type="audio/ogg", cfg=cfg)
    assert isinstance(res, dict)
    assert "ok" in res


def test_whatsapp_hindi_approval_card():
    cfg = Config.load()
    fc = Forecast(
        service="checkout-service",
        current_p99_ms=480.0,
        slope_ms_per_s=18.5,
        seconds_to_breach=18.2,
        breaching_now=False,
        confidence=0.92,
        confident=True,
    )
    plan = {"action": "scale_out", "capacity_delta": 1}
    res = post_whatsapp_approval(fc, plan, cfg, recipient="919400245958", lang="hi-IN")
    assert isinstance(res, dict)
    assert "ok" in res
