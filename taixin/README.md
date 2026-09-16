# 泰欣老师 短视频 → Kenny 口播稿 管线

把 泰欣老师（李泰欣，YouTube @eintaixin / @mr.taixinsales，IG @eintaixin）的短视频
批量转成逐字稿，再提炼主题、用 Kenny 的声音重写成可直接口播的稿子。

```
taixin/
├── sources.json          # 抓哪些频道
├── list_videos.py        # ① 列出所有短视频 → data/videos.json（按播放量排序）
├── transcribe.py         # ② 下载音频 + faster-whisper → transcripts/<id>.md + data/transcripts.jsonl
├── ingest_analysis.py    # ②b 云端抓不到音频时：把 Higgsfield 视频分析结果落成逐字稿（见下）
├── write_scripts.py      # ③ 逐字稿 → Kenny 口播稿（Claude）→ scripts/<id>.md + scripts/INDEX.md
├── prompts/kenny_voice.md# Kenny 的声音 / 结构 / 原创红线（③ 的 system prompt，改这里调风格）
├── data/                 # 视频清单 + 逐字稿 jsonl
├── transcripts/          # 每条视频一份逐字稿（含时间轴）
└── scripts/              # 每条视频一份 Kenny 口播稿
```

## 安装

```bash
pip install -r ../requirements.txt yt-dlp imageio-ffmpeg deno
```
（`deno` 是 yt-dlp 解 YouTube 签名要的 JS 运行时；系统里有 ffmpeg 就不需要 imageio-ffmpeg。）

## 跑

```bash
cd taixin
python list_videos.py                 # 约 1 分钟，598 条
python transcribe.py --top 30         # 播放量前 30 条；CPU 上每条约 20–40 秒
python write_scripts.py               # 需要 ANTHROPIC_API_KEY；默认 claude-opus-5
```
三步都是增量的：做过的自动跳过，加 `--force` 重做。

## YouTube 在云端 / 服务器 IP 上抓不动怎么办

YouTube 对数据中心 IP 会要求「登录确认不是机器人」或直接 403。两种解法，任选：

1. **本机跑**（最简单）：在自己电脑上跑 `transcribe.py`，家用 IP 一般不会被拦。
2. **给 cookies**：浏览器装 "Get cookies.txt LOCALLY" 之类插件，登录 YouTube 后导出
   `cookies.txt`，然后 `python transcribe.py --top 30 --cookies cookies.txt`。
   同一份 cookies 也能抓 Instagram：`python list_videos.py --cookies cookies.txt`。
   ⚠️ cookies.txt 不要提交进 repo。

进阶：跑一个 [bgutil PO token 服务](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
（`pip install bgutil-ytdlp-pot-provider` + `node server/build/main.js`），然后
`export TAIXIN_POT_SERVER=http://127.0.0.1:4416`。能解 403，但解不了「登录确认」。

## 云端替代路：Higgsfield 视频分析（本次首批 29 条就是这样来的）

在 Claude Code 里，Higgsfield MCP 的 `video_analysis_create(youtube_url)` 能在服务端直接吃 YouTube
链接（免费额度也能跑，每条约 1–2 分钟），返回逐场景的口播内容——注意是**英文转述**，不是中文逐字。
把返回的 scenes 存成 `data/analyses/<video_id>.json`（只要 audio / label / timestamp 三个字段），
然后 `python ingest_analysis.py` 落成 `transcripts/<id>.md`。纯音乐、无口播的片子把 status 写成
`skipped`。写口播稿只需要主题和洞察，英文转述已经够用；要中文逐字稿再走本机 yt-dlp + whisper。

## 转写质量

- 默认 `small` 模型，台湾腔中文够用；要更准用 `--model medium`（慢 3 倍）。
- 逐字稿是繁体口语原样，只做素材，不做发布。

## 口播稿的原创原则

`prompts/kenny_voice.md` 里写死了：只拿主题和洞察，不拿句子、例子、比喻；销售语境一律转译成
Kenny 的「高效生活 / 自我选择」语境；转译不了的标「不适合 Kenny」。每篇稿末尾有原创自检备注。
