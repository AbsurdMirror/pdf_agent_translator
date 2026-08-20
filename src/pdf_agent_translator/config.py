# -*- coding: utf-8 -*-
"""配置与密钥加载。

\\file 覆盖序：defaults < ``~/.pdf_agent_translator/config.toml`` < 仓库根
``config.toml`` < 当前目录 ``pdf_agent_translator.toml`` < ``--config`` < 环境变量。
独立仓库不读取工作区旁路的探测密钥文件。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """从某文件向上找到本项目根（含 name=pdf_agent_translator 的 pyproject）。

    \\param start 起点，默认本文件。
    \\return project_root。
    \\throws FileNotFoundError 找不到。
    """

    cursor = (start or Path(__file__)).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for folder in [cursor, *cursor.parents]:
        pyproject = folder / "pyproject.toml"
        if not pyproject.is_file():
            continue
        text = pyproject.read_text(encoding="utf-8")
        if 'name = "pdf_agent_translator"' in text:
            return folder
    raise FileNotFoundError("找不到 pdf_agent_translator 的 pyproject.toml")


_SECTION_RE = re.compile(r"^\[([A-Za-z0-9_.-]+)\]\s*$")
_KV_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*=\s*(.*)$")


def _strip_value(raw: str) -> str:
    """去掉 toml 值的引号与行尾注释。"""

    text = raw.strip()
    if text and text[0] not in {"'", '"'}:
        text = text.split("#", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_simple_toml(path: Path) -> dict[str, dict[str, str]]:
    """解析本项目用的扁平 toml 子集。

    \\param path 文件路径。
    \\return section -> key -> value。
    """

    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        sec = _SECTION_RE.match(stripped)
        if sec:
            current = sec.group(1)
            sections.setdefault(current, {})
            continue
        kv = _KV_RE.match(stripped)
        if not kv or current is None:
            continue
        sections[current][kv.group(1)] = _strip_value(kv.group(2))
    return sections


@dataclass
class AliyunSettings:
    """阿里云 DocMind。"""

    access_key_id: str = ""
    access_key_secret: str = ""
    endpoint: str = "docmind-api.cn-hangzhou.aliyuncs.com"


@dataclass
class LlmSettings:
    """翻译模型。默认按用户已验证的 MiniMax-M3。"""

    provider: str = "litellm"
    client: str = "custom"
    model_name: str = "MiniMax-M3"
    api_key: str = ""
    base_url: str = "https://api.minimaxi.com/v1"
    context_tokens: int = 204800
    max_output_tokens: int = 4096
    request_timeout_seconds: int = 120


@dataclass
class TranslateSettings:
    """翻译循环。"""

    source_lang: str = "en"
    target_lang: str = "zh"
    domain: str = "academic_paper"
    write_yaml: bool = False
    context_window_blocks: int = 10
    stop_on_block_error: bool = False


@dataclass
class Settings:
    """运行时完整配置。"""

    aliyun: AliyunSettings = field(default_factory=AliyunSettings)
    llm: LlmSettings = field(default_factory=LlmSettings)
    translate: TranslateSettings = field(default_factory=TranslateSettings)


def _merge_section(target: dict[str, str], incoming: dict[str, str] | None) -> None:
    """把 incoming 盖到 target 上，忽略空串。"""

    if not incoming:
        return
    for key, value in incoming.items():
        if value != "":
            target[key] = value


def _as_bool(value: str, default: bool) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str, default: int) -> int:
    if value == "":
        return default
    return int(value)


def iter_config_files(
    *,
    project_root: Path,
    cwd: Path,
    home: Path,
    extra: Path | None = None,
) -> list[Path]:
    """返回按覆盖序排列的配置文件候选（后出现的优先级更高）。

    \\param project_root 本仓库根。
    \\param cwd 进程当前目录。
    \\param home 用户主目录。
    \\param extra ``--config`` 指定的文件。
    \\return 候选路径列表，不要求文件存在。
    """

    paths = [
        home / ".pdf_agent_translator" / "config.toml",
        project_root / "config.toml",
        cwd / "pdf_agent_translator.toml",
    ]
    if extra is not None:
        paths.append(extra)
    return paths


def load_settings(config_path: Path | None = None) -> Settings:
    """按覆盖序加载 Settings。

    \\param config_path ``--config``，优先级高于 cwd / 主目录。
    \\return 填好的 Settings。
    """

    aliyun: dict[str, str] = {}
    llm: dict[str, str] = {}
    translate: dict[str, str] = {}

    try:
        project_root = find_project_root()
    except FileNotFoundError:
        project_root = Path.cwd()

    for candidate in iter_config_files(
        project_root=project_root,
        cwd=Path.cwd(),
        home=Path.home(),
        extra=config_path,
    ):
        if candidate.is_file():
            parsed = parse_simple_toml(candidate)
            _merge_section(aliyun, parsed.get("aliyun"))
            _merge_section(llm, parsed.get("llm"))
            _merge_section(translate, parsed.get("translate"))

    if os.environ.get("ALIYUN_ACCESS_KEY_ID"):
        aliyun["access_key_id"] = os.environ["ALIYUN_ACCESS_KEY_ID"]
    if os.environ.get("ALIYUN_ACCESS_KEY_SECRET"):
        aliyun["access_key_secret"] = os.environ["ALIYUN_ACCESS_KEY_SECRET"]
    if os.environ.get("ALIYUN_DOCMIND_ENDPOINT"):
        aliyun["endpoint"] = os.environ["ALIYUN_DOCMIND_ENDPOINT"]
    env_key = os.environ.get("PDF_TRANSLATE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if env_key:
        llm["api_key"] = env_key
    if os.environ.get("PDF_TRANSLATE_LLM_BASE_URL"):
        llm["base_url"] = os.environ["PDF_TRANSLATE_LLM_BASE_URL"]
    if os.environ.get("PDF_TRANSLATE_LLM_MODEL"):
        llm["model_name"] = os.environ["PDF_TRANSLATE_LLM_MODEL"]

    endpoint = aliyun.get("endpoint", "docmind-api.cn-hangzhou.aliyuncs.com")
    endpoint = endpoint.replace("https://", "").replace("http://", "").rstrip("/")

    return Settings(
        aliyun=AliyunSettings(
            access_key_id=aliyun.get("access_key_id", ""),
            access_key_secret=aliyun.get("access_key_secret", ""),
            endpoint=endpoint,
        ),
        llm=LlmSettings(
            provider=llm.get("provider", "litellm"),
            client=llm.get("client", "custom"),
            model_name=llm.get("model_name", "MiniMax-M3"),
            api_key=llm.get("api_key", ""),
            base_url=llm.get("base_url", "https://api.minimaxi.com/v1"),
            context_tokens=_as_int(llm.get("context_tokens", ""), 204800),
            max_output_tokens=_as_int(llm.get("max_output_tokens", ""), 4096),
            request_timeout_seconds=_as_int(llm.get("request_timeout_seconds", ""), 120),
        ),
        translate=TranslateSettings(
            source_lang=translate.get("source_lang", "en"),
            target_lang=translate.get("target_lang", "zh"),
            domain=translate.get("domain", "academic_paper"),
            write_yaml=_as_bool(translate.get("write_yaml", ""), False),
            context_window_blocks=_as_int(translate.get("context_window_blocks", ""), 10),
            stop_on_block_error=_as_bool(translate.get("stop_on_block_error", ""), False),
        ),
    )


def lang_display(code: str) -> str:
    """短码展开成提示词用的语言名。

    \\param code ``en`` / ``zh`` 等。
    \\return English / Chinese / 原文。
    """

    mapping = {
        "en": "English",
        "zh": "Chinese",
        "zh-cn": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
    }
    return mapping.get((code or "").lower(), code or "English")
