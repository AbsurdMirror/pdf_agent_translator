# PDF Agent Translator

把 PDF 解析成结构化块，按块翻译，生成可离线阅读的双语 HTML。

- **解析**：阿里云 DocMind（VLM 增强）
- **翻译**：OpenAI 兼容接口（已验证 MiniMax-M3，请求关闭思考）
- **阅读**：`document.html` + 同目录 `figures/`。文章模式 / 编辑模式、目录、对照高亮

本仓库可独立克隆使用，不附带参考实现或密钥。

## 要求

- Python 3.10+
- 阿里云 AccessKey，并开通 **文档智能 / DocMind**
- OpenAI 兼容 LLM（`api_key` / `base_url` / `model_name`）

## 安装

```bash
git clone https://github.com/AbsurdMirror/pdf_agent_translator.git
cd pdf_agent_translator
python -m venv .venv
```

```text
Windows:  .venv\Scripts\activate
Unix:     source .venv/bin/activate
```

```bash
pip install -e ".[dev]"
```

## 配置

复制示例，填入密钥（`config.toml` 已 gitignore，**不要提交**）：

```bash
cp config.example.toml config.toml
```

Windows PowerShell：

```powershell
Copy-Item config.example.toml config.toml
```

```toml
[aliyun]
access_key_id = "LTAI..."
access_key_secret = "..."
endpoint = "docmind-api.cn-hangzhou.aliyuncs.com"

[llm]
model_name = "MiniMax-M3"
api_key = "sk-..."
base_url = "https://api.minimaxi.com/v1"
max_output_tokens = 4096
request_timeout_seconds = 120
```

覆盖顺序（后者覆盖前者）：默认值 < `~/.pdf_agent_translator/config.toml` < 仓库根 `config.toml` < 当前目录 `pdf_agent_translator.toml` < `--config` < 环境变量。

环境变量：`ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET`、`PDF_TRANSLATE_LLM_API_KEY`（或 `OPENAI_API_KEY`）、`PDF_TRANSLATE_LLM_BASE_URL`、`PDF_TRANSLATE_LLM_MODEL`。

本机若配置了 SOCKS 代理，翻译请求会忽略环境代理直连（避免缺 `socksio` 直接失败）。

## 用法

```bash
# 解析 + 翻译 + 渲染
python -m pdf_agent_translator.cli paper.pdf --src en --tgt zh --out ./out

# 断点续跑（从第一个 pending/failed 块继续）
python -m pdf_agent_translator.cli paper.pdf --resume --out ./out

# 只整理标题目录、表格/代码围栏，并重渲 HTML
python -m pdf_agent_translator.cli --out ./out --polish --force

# 只重渲 HTML
python -m pdf_agent_translator.cli --out ./out --render-only --force

# 本机 HTTP 打开（豆包等浏览器插件才能划词；不要双击 file://）
python -m pdf_agent_translator.cli --out ./out --serve

# 简易 GUI
python -m pdf_agent_translator.gui
# 或 pdf-translate-gui
```

常用参数：`--config`、`--parse-only`、`--translate-only`、`--retranslate-failed`、`--strict`、`--port`（配合 `--serve`，默认 8765）、`--open`（完成后用系统浏览器打开 HTML）。

## 输出目录

```text
out/
  source.pdf
  job.toml              # 阶段
  parse_raw.json        # DocMind 原始 layout
  document.json         # 权威：原文/译文/目录
  figures/              # 解析下来的图
  document.html         # 阅读器（须与 figures/ 一起）
```

阅读器：

- 默认文章模式；勾选 **编辑模式** 进入分块审阅（页码/类型、改原文译文）
- 双语对照：上下（一段原文紧跟译文）或左右；悬停对应高亮
- 侧栏目录可折叠，章节可收起
- 图注/表题仅认 DocMind 的 `figure_name` / `figure_note` / `table_name` / `table_note`
- 浏览器里的修改要点「下载 JSON/HTML」才保存；`--render` 默认不覆盖更新过的 HTML（加 `--force`）

## 测试

```bash
pytest
```

不调用真实阿里云 / LLM。GitHub Actions 会在 Python 3.10 / 3.11 / 3.12 上跑同一套测试。

## 仓库范围

提交内容只有本工具源码、测试、`config.example.toml`、许可证。下列内容**不在本仓库**：

- 密钥、`config.toml`、`.env`
- 解析/翻译产物（`out/`、HTML、PDF）
- 参考实现或其他翻译工具仓库

## 许可

MIT，见 [LICENSE](LICENSE)。
