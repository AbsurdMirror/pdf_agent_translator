# -*- coding: utf-8 -*-
"""pdf-translate 命令行。

\\file CLI 是源真相；GUI 只包装同一条 Pipeline。
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from pdf_agent_translator.pipeline import Pipeline, RunRequest, build_pipeline
from pdf_agent_translator.models import JobPhase


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PDF 解析 + 翻译 + 离线 HTML")
    parser.add_argument("pdf", nargs="?", help="输入 PDF")
    parser.add_argument("--src", default="en", help="源语言短码")
    parser.add_argument("--tgt", default="zh", help="目标语言短码")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--config", type=Path, default=None, help="密钥/配置 toml")
    parser.add_argument("--resume", action="store_true", help="从第一个 pending|failed 继续")
    parser.add_argument("--retranslate", action="store_true")
    parser.add_argument("--retranslate-failed", action="store_true")
    parser.add_argument("--yaml", action="store_true")
    parser.add_argument("--open", action="store_true", help="完成后用 file:// 打开 HTML")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="用本机 http://127.0.0.1 打开（豆包等插件才能划词）",
    )
    parser.add_argument("--port", type=int, default=8765, help="--serve 端口")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--force", action="store_true", help="覆盖较新的 HTML")
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--translate-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--polish", action="store_true", help="整理标题目录并修补表格/代码围栏，不重译")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    \\return 0 成功；2 参数；3 解析失败；4 strict 未完成；1 其它。
    """

    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    out_dir = Path(args.out)
    pdf = Path(args.pdf) if args.pdf else None
    serve_only = args.serve and not args.pdf and not args.render_only and not args.polish and not args.translate_only
    if serve_only:
        return _serve_out_dir(out_dir, args.port)
    if not args.translate_only and not args.render_only and not args.polish:
        if pdf is None or not pdf.is_file():
            parser.error("需要存在的 PDF 路径")
            return 2

    def on_progress(p) -> None:
        print(f"[{p.stage} {p.percent:3d}%] {p.message}", flush=True)

    try:
        pipe: Pipeline = build_pipeline(args.config, on_progress=on_progress)
        job = pipe.run(
            RunRequest(
                pdf_path=pdf,
                out_dir=out_dir,
                source_lang=args.src,
                target_lang=args.tgt,
                resume=args.resume,
                retranslate=args.retranslate,
                retranslate_failed=args.retranslate_failed,
                write_yaml=args.yaml,
                strict=args.strict,
                force_render=args.force,
                config_path=args.config,
                cancel_event=threading.Event(),
                parse_only=args.parse_only,
                translate_only=args.translate_only,
                render_only=args.render_only,
                polish=args.polish,
            )
        )
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        logging.exception("失败")
        text = str(exc).lower()
        if "docmind" in text or "解析" in text:
            return 3
        return 1

    print(f"完成 phase={job.phase.value} html={job.html_path}")
    if args.serve:
        return _serve_out_dir(out_dir, args.port)
    if args.open and job.html_path.is_file():
        import webbrowser

        webbrowser.open(job.html_path.resolve().as_uri())
    if args.strict and job.phase == JobPhase.failed:
        return 4
    return 0


def _serve_out_dir(out_dir: Path, port: int) -> int:
    """在输出目录起一个只读 HTTP 服务，让浏览器扩展能注入。

    \\brief file:// 下 Chrome 默认不跑插件；http://127.0.0.1 可以划词问豆包。
    """

    import functools
    import http.server
    import socketserver
    import webbrowser

    html_path = out_dir / "document.html"
    if not html_path.is_file():
        print(f"没有 {html_path}，先渲染再 --serve", file=sys.stderr)
        return 2
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir.resolve()))
    try:
        httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"端口 {port} 不可用: {exc}", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{port}/document.html"
    print(f"本机阅读（插件可用）: {url}")
    print("Ctrl+C 结束服务")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
