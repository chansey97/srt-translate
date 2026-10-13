# SRT 字幕翻译工具

通过 OpenAI Compatible API 翻译 SRT 字幕，支持统一术语、人工校对和分阶段续跑。源语言必填，默认译为简体中文（`zh-Hans`），原字幕文件保持不变。详细设计见[仓库中的 PLAN.md](https://github.com/chansey97/srt-translate/blob/main/PLAN.md)。

## 六阶段流程

```mermaid
flowchart TD
    A[原始 SRT] --> B["1. extract：抽取条目"]
    B --> C["entries：原文分片"]
    C --> D["2. discover：发现实体、生成译名和打分"]
    D --> E["entities：实体分片"]
    E --> F["3. glossary：按置信度统一译名"]
    F --> G["glossary.json"]
    C --> H["4. subsets：按原文匹配 glossary 候选"]
    G --> H
    H --> I["glossary_subsets：分片候选术语表"]
    C --> J["5. translate：加入术语表及双语历史后翻译"]
    I --> J
    J --> K["translations：核对数量和逐项 n 后保存"]
    K --> L["6. backfill：按原出现顺序回填"]
    A --> L
    L --> M["backfill/原文件名.srt"]
    Z["可选背景文本"] -.-> D
    Z -.-> J
    G -.-> R["可选：编辑全局 glossary"]
    R -.-> H
    I -.-> S["可选：编辑当前分片的术语表"]
    S -.-> J
```

## 安装

### Windows x64 portable

从 [Releases](https://github.com/chansey97/srt-translate/releases) 下载 `srt-translate-windows-x64.zip`，完整解压后即可运行，无需安装 Python。应用目录如下；移动应用时保留整个目录：

```text
srt-translate/
├── srt-translate.exe
├── _internal/
├── config.toml
└── README.md
```

编辑 exe 同目录的 `config.toml`，填写 API 服务信息。在该目录打开 PowerShell，运行：

```powershell
.\srt-translate.exe --help
.\srt-translate.exe "D:\字幕\示例 🎬.srt" --source-lang en --output-dir "D:\字幕\译文"
```

下文的 `srt-translate` 命令同样适用于 portable；在 PowerShell 中替换为 `.\srt-translate.exe` 或 exe 的完整路径。

### Python 安装

需要 Git 和 Python 3.11 或以上版本。以下命令以 Windows PowerShell 为例。

先克隆项目并进入项目目录：

```
git clone https://github.com/chansey97/srt-translate.git
cd srt-translate
```

创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

选择一种安装方式：

| 方式 | 命令 | 说明 |
| --- | --- | --- |
| 普通安装 | `python -m pip install .` | 用于运行工具 |
| 开发安装 | `python -m pip install -e ".[dev]"` | 可编辑安装，包含测试依赖 |

安装后可运行 `srt-translate --help` 查看帮助。

## 配置

API 服务及模型需支持 OpenAI Chat Completions 和 `json_schema` 结构化输出。在 UTF-8 编码的 `config.toml` 中填写 API 参数。以下为内置默认值，请按服务提供的信息修改：

```toml
[openai]
base_url = "http://127.0.0.1:8317/v1"
api_key = "123456"
model = "gemini-3.8-flash-high"
max_retries = 2
```

`max_retries` 为 API 请求的最大重试次数，必须是非负整数。使用指定配置文件：

```powershell
srt-translate input.srt --source-lang en --config-file ./config.toml
```

配置按字段叠加，后者只覆盖自己填写的字段：

| 优先级 | Python 安装 | Portable |
| --- | --- | --- |
| 低 | 包内 `config.default.toml` | 包内 `config.default.toml` |
| 中 | 系统用户配置目录中的 `srt-translate/config.toml` | exe 同目录的 `config.toml` |
| 高 | `--config-file PATH` 指定的文件 | `--config-file PATH` 指定的文件 |

Python 安装的用户配置文件可自行创建，以下命令显示其完整路径：

```powershell
python -c "from platformdirs import user_config_path; print(user_config_path('srt-translate', appauthor=False) / 'config.toml')"
```

Portable 不读取系统用户配置，只按 exe 的实际位置查找同目录配置，启动时的工作目录不影响此位置。程序不会额外搜索当前工作目录中的 `config.toml`；其他配置位置需用 `--config-file` 指定。中间层配置不存在时跳过；显式指定的文件缺失，或配置存在语法、类型及未知字段错误时，会在运行前报错。

## 使用

### 典型用法

英文翻译为简体中文：

```powershell
srt-translate "examples/Blood.of.Zeus.S01E01.srt" --source-lang en
```

日文翻译为英文，并指定输出父目录：

```powershell
srt-translate "examples/1997 スペシャルおまけビデオ.srt" --source-lang ja --target-lang en --output-dir outputs
```

提供作品背景和文风参考：

```powershell
srt-translate input.srt --source-lang en --background background.md
```

输出父目录默认为当前工作目录，等价于 `--output-dir ./`。程序自动在其中创建 `<stem>__<source_lang>_to_<target_lang>/` 任务目录。第一条命令的最终字幕位于：

```text
Blood.of.Zeus.S01E01__en_to_zh-Hans/backfill/Blood.of.Zeus.S01E01.srt
```

所有相对路径基于当前工作目录。同名字幕使用相同语言组合时，请指定不同的输出父目录以区分任务。

标准输出和错误输出统一使用 UTF-8，支持中文及 emoji 路径。通过管道、文件重定向或 `subprocess` 捕获时，接收端应按 UTF-8 解码。

### CLI 参数

```text
srt-translate INPUT_SRT --source-lang LANG [--target-lang LANG] [OPTIONS]
```

`LANG` 使用 BCP 47 语言标签：`en`（英语）、`ja`（日语）、`zh-Hans`（简体中文）、`zh-Hant`（繁体中文）。标签的各部分用连字符 `-` 连接，例如 `en-US`（美式英语）。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `INPUT_SRT` | 必填 | 原始 SRT 路径，各阶段均需提供 |
| `--source-lang LANG` | 必填 | 源语言的 BCP 47 标签 |
| `--target-lang LANG` | `zh-Hans` | 目标语言的 BCP 47 标签 |
| `--background PATH` | 不提供 | UTF-8 背景文本，无扩展名限制 |
| `--output-dir PATH` | 当前工作目录 | 输出父目录，任务目录名自动追加 |
| `--config-file PATH` | 不提供 | 配置覆盖文件，优先级最高 |
| `--input-encoding NAME` | `utf-8-sig` | 原 SRT 编码，默认兼容带 BOM 和不带 BOM 的 UTF-8 |
| `--chunk-size N` | `20` | 每片字幕条数，正整数 |
| `--history-size N` | `5` | 参考的前文双语字幕条数，`0` 禁用 |
| `--no-translate-glossary` | 不启用 | 将模型确认适用的候选术语保留原词 |
| `--delay-between-requests SECONDS` | `0` | 每次模型调用前的等待秒数，含第一次；支持非负小数 |
| `--from-stage NAME` | `extract` | 起始阶段，包含该阶段 |
| `--to-stage NAME` | `backfill` | 结束阶段，包含该阶段 |
| `-h` / `--help` | — | 显示帮助 |

阶段顺序为 `extract → discover → glossary → subsets → translate → backfill`。程序只执行所选区间，不补跑前置阶段。

### 检查、编辑与续跑

先生成全局术语表，可以新增、删除词条或修改译名，然后继续：

```powershell
srt-translate input.srt --source-lang en --to-stage glossary
# 编辑任务目录中的 glossary.json
srt-translate input.srt --source-lang en --from-stage subsets
```

也可以停在分片术语表阶段，逐片调整后再翻译：

```powershell
srt-translate input.srt --source-lang en --to-stage subsets
# 编辑任务目录中 glossary_subsets/ 下的文件
srt-translate input.srt --source-lang en --from-stage translate
```

术语表采用 `"原词": "译名"` 格式；若需保留个别原词，将键和值设为相同，例如 `"Alexia": "Alexia"`。

分片术语表从原文匹配全局词条，不依赖该片是否发现过实体。匹配忽略大小写和空白差异，保留原始键值；命中的词条仅是候选。例如 `Orc` 可能因 `force` 入选，模型应忽略这种无关匹配。默认模式对确认适用的术语严格使用指定译名，`--no-translate-glossary` 则保留其原文写法。

任务中断后，重新运行原命令即可续跑。已有产物会跳过，修改上游内容不会自动更新后续产物。需要重新生成时，按下表处理；删除产物会丢失其中的人工编辑。表中路径均相对于任务目录。

| 修改内容 | 处理方式 | 续跑起点 |
| --- | --- | --- |
| 原 SRT、输入编码或分片大小 | 使用新的输出父目录 | `extract` |
| 背景或模型 | 删除 `entities/`、`glossary.json`、`glossary_subsets/`、`translations/`、`backfill/` | `discover` |
| `glossary.json` 词条的新增、删除或译名修改 | 删除 `glossary_subsets/`、`translations/`、`backfill/` | `subsets` |
| 分片术语表、术语开关或历史条数 | 删除 `translations/`、`backfill/` | `translate` |
| `translations/` 中的译文 | 删除 `backfill/` | `backfill` |

续跑时保持输入、语言、配置、背景和输出父目录等参数一致。编辑译文时保留条目数量、顺序和 `n`（字幕编号）。例如，只重新回填已编辑的译文：

```powershell
# 先删除当前任务目录中的 backfill/
srt-translate input.srt --source-lang en --from-stage backfill
```

## 测试

完成开发安装后，运行默认测试，不发送 API 请求：

```powershell
python -m pytest
```

真实 API 测试使用内置配置和系统用户配置，并保留产物至 `test_outputs/live/`：

```powershell
python -m pytest tests/live
```

## 构建 Windows x64 portable

Release 使用 Python 3.14 x64；本地构建建议使用相同版本。在项目根目录准备 `.venv`，手动安装锁定的构建、运行和测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration
.\build_portable.bat
.\.venv\Scripts\python.exe -m pytest tests/portable
```

各条命令成功后再执行下一条。修改源码后，先重新安装当前项目再测试。`build_portable.bat` 也可双击运行：它检查 Windows、x64 Python 和 PyInstaller，使用项目 `.venv` 构建，不下载或安装依赖。执行成功或失败后均暂停；存在 `CI` 环境变量时跳过暂停。

PyInstaller 使用 `--onedir --console`。中间文件位于 `build/portable/`，完整应用位于 `dist/srt-translate/`，发行包为 `dist/srt-translate-windows-x64.zip`。重复构建会重建该应用目录和 ZIP；随包的 `config.toml` 始终从包内默认配置复制，请将个人配置另存。ZIP 包含完整应用目录及本 README，不含 `PLAN.md`；仓库中的设计文档保留。

`tests/portable` 需要先构建 ZIP；测试从含中文、空格和 emoji 的目录解压并启动 exe，验证配置加载、UTF-8 输出、退出码及完整翻译流程。模型请求仅发往测试创建的本机假 API，不连接真实服务。
