# -*- coding: utf-8 -*-
"""配置装载与组件工厂：按名称从注册表动态实例化四个抽象层组件。

配置文件（JSON，默认 ./config.json）：
{
  "trigger":   {"impl": "stdin",    "params": {"prompt": ">>> "}},
  "corrector": {"impl": "identity", "params": {}},
  "agent":     {"impl": "mock",     "params": {"token_delay": 0.25}},
  "output":    {"impl": "printer",  "params": {"char_delay": 0.08}},
  "session":   {"params": {"verbose": true}}
}
"""
from __future__ import annotations

import importlib
import json
import os

from .agent import AGENT_IMPLS
from .corrector import CORRECTOR_IMPLS
from .output import OUTPUT_IMPLS
from .trigger import TRIGGER_IMPLS

REGISTRIES = {
    "trigger": TRIGGER_IMPLS,
    "corrector": CORRECTOR_IMPLS,
    "agent": AGENT_IMPLS,
    "output": OUTPUT_IMPLS,
}

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


class ConfigError(Exception):
    pass


def load_config(path: str | None = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise ConfigError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for kind in REGISTRIES:
        if kind not in cfg:
            raise ConfigError(f"配置缺少节: {kind}")
        if "impl" not in cfg[kind]:
            raise ConfigError(f"配置节 {kind} 缺少 impl")
    return cfg


def build(kind: str, cfg: dict):
    """按注册表动态实例化第 kind 层的配置指定实现。params 作为构造参数展开。"""
    registry = REGISTRIES[kind]
    impl_name = cfg[kind]["impl"]
    entry = registry.get(impl_name)
    if entry is None:
        raise ConfigError(
            f"{kind} 层没有注册名为 {impl_name!r} 的实现，可用: {sorted(registry)}"
        )
    mod = importlib.import_module(entry["module"])
    cls = getattr(mod, entry["cls"])
    params = dict(cfg[kind].get("params", {}))
    try:
        return cls(**params)
    except TypeError as e:
        raise ConfigError(f"{kind}.{impl_name} 构造参数不匹配: {e}") from e


async def assemble(cfg: dict) -> dict:
    """按配置构建四层组件，并对每个组件调用可选初始化 Lifecycle.initialize()
    （顺序：输出 → 矫正 → Agent → 触发，底层先就绪）。返回组件字典。
    任一初始化失败即抛错终止装配，让配置问题早暴露。"""
    components = {
        "output": build("output", cfg),
        "corrector": build("corrector", cfg),
        "agent": build("agent", cfg),
        "trigger": build("trigger", cfg),
    }
    for kind, comp in components.items():
        try:
            await comp.initialize()
        except Exception as e:
            raise ConfigError(f"{kind} 组件初始化失败: {e}") from e
    return components
