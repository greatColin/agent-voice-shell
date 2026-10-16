# -*- coding: utf-8 -*-
"""矫正实现注册表。"""
from .base import TextCorrector  # noqa: F401
from .identity import IdentityCorrector  # noqa: F401

CORRECTOR_IMPLS = {
    "identity": {"module": "voice_agent.corrector.identity", "cls": "IdentityCorrector"},
}
