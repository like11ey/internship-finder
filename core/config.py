"""
配置加载器 —— 读取 config.yaml 并提供类型安全的访问
"""

import os
import yaml
from typing import Any, Optional

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

_config_cache: Optional[dict] = None


def load_config(path: str = CONFIG_PATH) -> dict:
    """加载 YAML 配置文件（带缓存）"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}\n"
                                f"请复制 config.yaml 模板并填写个人信息")
    with open(path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def reload_config(path: str = CONFIG_PATH) -> dict:
    """强制重新加载配置"""
    global _config_cache
    _config_cache = None
    return load_config(path)


def get_profile() -> dict:
    return load_config().get("profile", {})


def get_cities() -> list[str]:
    return load_config().get("cities", [])


def get_skills() -> dict[str, int]:
    """返回 {技能名: 熟练度}"""
    return load_config().get("skills", {})


def get_directions() -> list[str]:
    return load_config().get("job_directions", [])


def get_preferred_companies() -> list[str]:
    val = load_config().get("preferred_companies", [])
    return val if val else []


def get_collector_config() -> dict:
    return load_config().get("collector", {})


def get_matcher_config() -> dict:
    return load_config().get("matcher", {})


def get_output_config() -> dict:
    return load_config().get("output", {})
