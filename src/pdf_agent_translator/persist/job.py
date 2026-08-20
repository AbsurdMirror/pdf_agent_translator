# -*- coding: utf-8 -*-
"""Job 目录与 job.toml / document.json 原子读写。

\\file phase 权威在 job.toml；文档权威在 document.json。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pdf_agent_translator.models import Document, JobPhase, utc_now_iso


def _atomic_write_text(path: Path, text: str) -> None:
    """先写临时文件再 replace，避免写到一半崩溃。

    \\param path 目标路径。
    \\param text 完整文本。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def pdf_sha256(pdf_path: Path) -> str:
    """计算 PDF 前 8 位十六进制指纹。

    \\param pdf_path 源文件。
    \\return 8 位 hex。
    """

    digest = hashlib.sha256()
    with pdf_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:8]


def make_job_id(pdf_path: Path) -> str:
    """生成 job_id：UTC 时间 + PDF hash。

    \\param pdf_path 源 PDF。
    \\return 例如 20260814T120000_ab12cd34。
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{pdf_sha256(pdf_path)}"


@dataclass
class Job:
    """一次翻译任务在磁盘上的布局。"""

    job_id: str
    out_dir: Path
    phase: JobPhase
    pdf_sha256: str
    source_pdf_name: str
    error: str = ""

    @property
    def source_pdf(self) -> Path:
        return self.out_dir / "source.pdf"

    @property
    def job_toml(self) -> Path:
        return self.out_dir / "job.toml"

    @property
    def document_json(self) -> Path:
        return self.out_dir / "document.json"

    @property
    def parse_raw_json(self) -> Path:
        return self.out_dir / "parse_raw.json"

    @property
    def html_path(self) -> Path:
        return self.out_dir / "document.html"

    @property
    def figures_dir(self) -> Path:
        return self.out_dir / "figures"

    @property
    def logs_dir(self) -> Path:
        return self.out_dir / "logs"

    @property
    def qfaos_logs_dir(self) -> Path:
        return self.out_dir / "qfaos_logs"


def dump_job_toml(job: Job) -> None:
    """把 phase 写进 job.toml。

    \\param job 当前任务。
    """

    text = (
        f'job_id = "{job.job_id}"\n'
        f'phase = "{job.phase.value}"\n'
        f'pdf_sha256 = "{job.pdf_sha256}"\n'
        f'source_pdf_name = "{job.source_pdf_name}"\n'
        f'error = "{job.error.replace(chr(34), "")}"\n'
        f'updated_at = "{utc_now_iso()}"\n'
    )
    _atomic_write_text(job.job_toml, text)


def load_job_toml(out_dir: Path) -> Job:
    """从已有目录读 job.toml。

    \\param out_dir 输出目录。
    \\return Job。
    \\throws FileNotFoundError / ValueError。
    """

    path = out_dir / "job.toml"
    if not path.is_file():
        raise FileNotFoundError(f"没有 job.toml: {path}")
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, raw = line.split("=", 1)
        data[key.strip()] = raw.strip().strip('"')
    return Job(
        job_id=data.get("job_id", ""),
        out_dir=out_dir,
        phase=JobPhase(data.get("phase", "created")),
        pdf_sha256=data.get("pdf_sha256", ""),
        source_pdf_name=data.get("source_pdf_name", ""),
        error=data.get("error", ""),
    )


def save_document(path: Path, document: Document) -> None:
    """原子写 document.json。

    \\param path JSON 路径。
    \\param document 文档。
    """

    payload = document.model_dump(mode="json")
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_document(path: Path) -> Document:
    """读 document.json。

    \\param path JSON 路径。
    \\return Document。
    """

    return Document.model_validate_json(path.read_text(encoding="utf-8"))


def prepare_out_dir(pdf_path: Path, out_dir: Path, *, resume: bool) -> Job:
    """创建或校验输出目录。

    \\brief 同 out 不同 PDF hash 且非 resume 则拒绝。
    \\param pdf_path 源 PDF。
    \\param out_dir 输出目录。
    \\param resume 是否续跑。
    \\return Job。
    \\throws ValueError 目录被另一份 PDF 占用。
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    digest = pdf_sha256(pdf_path)
    job_file = out_dir / "job.toml"
    if job_file.is_file():
        job = load_job_toml(out_dir)
        if job.pdf_sha256 and job.pdf_sha256 != digest:
            raise ValueError(
                f"--out {out_dir} 已绑定 PDF {job.source_pdf_name} ({job.pdf_sha256})，"
                f"与当前文件 ({digest}) 不同。换目录或加 --resume 且确认是同一文件。"
            )
        if not resume and job.phase not in {JobPhase.created}:
            # 允许覆盖同 PDF 重跑：调用方用 resume 或新目录。
            pass
        return job

    job = Job(
        job_id=make_job_id(pdf_path),
        out_dir=out_dir,
        phase=JobPhase.created,
        pdf_sha256=digest,
        source_pdf_name=pdf_path.name,
    )
    dest = job.source_pdf
    if not dest.exists() or dest.stat().st_size != pdf_path.stat().st_size:
        shutil.copy2(pdf_path, dest)
    job.logs_dir.mkdir(exist_ok=True)
    job.figures_dir.mkdir(exist_ok=True)
    dump_job_toml(job)
    return job
