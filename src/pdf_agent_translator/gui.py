# -*- coding: utf-8 -*-
"""tkinter 薄包装：选 PDF / 语言 / 输出目录，worker 线程跑 Pipeline。

\\file 取消只 set 同一把 cancel_event。
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pdf_agent_translator.pipeline import Progress, RunRequest, build_pipeline


def main() -> int:
    """启动 GUI。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = tk.Tk()
    root.title("PDF Agent Translator")
    root.geometry("640x280")

    pdf_var = tk.StringVar()
    out_var = tk.StringVar()
    src_var = tk.StringVar(value="en")
    tgt_var = tk.StringVar(value="zh")
    status_var = tk.StringVar(value="就绪")
    cancel_event = threading.Event()
    busy = {"v": False}

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    def pick_pdf() -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            pdf_var.set(path)
            if not out_var.get():
                out_var.set(str(Path(path).with_suffix("")) + "_out")

    def pick_out() -> None:
        path = filedialog.askdirectory()
        if path:
            out_var.set(path)

    ttk.Label(frm, text="PDF").grid(row=0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=pdf_var, width=60).grid(row=0, column=1, sticky="ew")
    ttk.Button(frm, text="选择", command=pick_pdf).grid(row=0, column=2)

    ttk.Label(frm, text="输出").grid(row=1, column=0, sticky="w")
    ttk.Entry(frm, textvariable=out_var, width=60).grid(row=1, column=1, sticky="ew")
    ttk.Button(frm, text="选择", command=pick_out).grid(row=1, column=2)

    ttk.Label(frm, text="源语言").grid(row=2, column=0, sticky="w")
    ttk.Entry(frm, textvariable=src_var, width=8).grid(row=2, column=1, sticky="w")
    ttk.Label(frm, text="目标语言").grid(row=3, column=0, sticky="w")
    ttk.Entry(frm, textvariable=tgt_var, width=8).grid(row=3, column=1, sticky="w")

    bar = ttk.Progressbar(frm, mode="determinate", maximum=100)
    bar.grid(row=4, column=0, columnspan=3, sticky="ew", pady=12)
    ttk.Label(frm, textvariable=status_var).grid(row=5, column=0, columnspan=3, sticky="w")

    def on_progress(p: Progress) -> None:
        # 必须 marshal 回主线程，否则 Tk 卡死/花屏。
        root.after(0, lambda: (bar.configure(value=p.percent), status_var.set(f"{p.stage}: {p.message}")))

    def work() -> None:
        try:
            pipe = build_pipeline(None, on_progress=on_progress)
            job = pipe.run(
                RunRequest(
                    pdf_path=Path(pdf_var.get()),
                    out_dir=Path(out_var.get()),
                    source_lang=src_var.get(),
                    target_lang=tgt_var.get(),
                    resume=True,
                    cancel_event=cancel_event,
                )
            )
            if job.html_path.is_file():
                import webbrowser

                webbrowser.open(job.html_path.resolve().as_uri())
            root.after(0, lambda: status_var.set(f"完成 {job.phase.value}"))
        except Exception as exc:
            root.after(0, lambda: messagebox.showerror("失败", str(exc)))
        finally:
            busy["v"] = False

    def start() -> None:
        if busy["v"]:
            return
        if not pdf_var.get() or not out_var.get():
            messagebox.showwarning("缺少路径", "请选择 PDF 和输出目录")
            return
        cancel_event.clear()
        busy["v"] = True
        threading.Thread(target=work, daemon=True).start()

    def cancel() -> None:
        cancel_event.set()
        status_var.set("已请求取消（当前块结束后停）")

    ttk.Button(frm, text="开始", command=start).grid(row=6, column=1, sticky="w")
    ttk.Button(frm, text="取消", command=cancel).grid(row=6, column=1, padx=80, sticky="w")
    frm.columnconfigure(1, weight=1)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
