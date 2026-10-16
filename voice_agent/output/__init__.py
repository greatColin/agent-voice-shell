# -*- coding: utf-8 -*-
"""输出通道实现注册表。"""
from .base import POISON, OutputChannel  # noqa: F401
from .gui import GuiPrinterChannel  # noqa: F401
from .printer import PrinterChannel  # noqa: F401

OUTPUT_IMPLS = {
    "printer": {"module": "voice_agent.output.printer", "cls": "PrinterChannel"},
    "gui": {"module": "voice_agent.output.gui", "cls": "GuiPrinterChannel"},
}
