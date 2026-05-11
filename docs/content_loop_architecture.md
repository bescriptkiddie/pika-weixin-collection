# 人机共创内容生成闭环

这个项目的长期目标不只是“抓公众号”，而是形成一个以人为控制面、AI 为生产力放大器的本地内容生成器。

## 一句话定位

人决定信息源、话题和分发目标，AI 负责采集、整理、聚合和成稿；发布后的反馈再由人和 AI 一起复盘，反向修改来源、选题、评分和生成模板。

## 闭环总览

```text
人确定信息源 / 话题 / 受众
  -> AI 采集与整理
  -> 标准化内容池
  -> AI 辅助去重 / 标签 / 摘要 / 评分
  -> 人选择候选素材与角度
  -> AI 生成草稿
  -> 人审定、改写、分发
  -> 人 + AI 复盘反馈
  -> 修改信息源、话题、评分和生成模板
```

## 0. 人在闭环中的位置

这个系统不是全自动内容工厂。人的角色不是最后“审核一下”，而是贯穿闭环的控制面。

人负责：

- 选信息源：哪些公众号、GitHub 仓库、RSS、手动链接值得进入系统。
- 定话题：今天/本周要围绕什么问题生成内容。
- 选角度：同一批素材可以写成简报、观点文、教程、投研笔记或短内容。
- 改草稿：调整标题、结构、语气、删减风险内容。
- 给反馈：采纳、删除、不感兴趣、继续深挖、改写原因。

AI 负责：

- 扩大采集规模，降低人工找资料成本。
- 清洗、去重、摘要、打标签、聚类和初步评分。
- 根据人的话题和受众生成多版本草稿。
- 在反馈后提出下一轮来源、选题和模板调整建议。

真正的闭环成立条件：人的反馈不能只停留在前端状态里，必须写回后端，影响下一次素材排序、选题建议和生成模板。

## 1. 信息源层

信息源不应该都伪装成公众号。每类来源保留自己的采集方式，再统一转换成项目内部的标准内容格式。

当前已经有：

- 微信公众号：通过 `name2fakeid.json` 和微信后台接口抓取文章列表、正文、封面。
- B 站视频：通过 `bilibili_video` 信源读取视频元信息和官方字幕；无字幕时可下载音频并交给云端 ASR provider 转写。
- 播客 RSS：通过 `podcast_feed` 信源读取节目列表、shownotes 和音频链接；需要全文时可开启云端音频转写。
- GitHub 仓库：通过 `github_repo` 信源抓 README、docs 和 releases。
- 本地 Markdown 导出：通过 `scripts/export_markdown.py` 把已采集内容转成可迁移文件。
- llm_wiki sources 导出：通过 `src/llm_wiki_bridge/export_sources.py` 把公众号文章转成 `raw/sources/wechat/**/*.md`，这是知识库导出路径，不是外部信源主路径。

下一步可扩展：

- RSS / Atom：博客、媒体、个人站点。
- 手动收藏：用户粘贴链接或 Markdown，作为高意图输入。
- 其他平台：Telegram、X、Reddit、HN 等，按需做独立适配器。

## 2. 采集适配器层

每个适配器只负责一件事：从某类源抓内容，并输出标准 `FetchedItem`。落盘文件只能作为 snapshot 或知识库导出，不应成为信源本身。

建议接口：

```text
SourceConfig
  id: horizon
  type: github_repo
  url: https://github.com/Thysrael/Horizon
  enabled: true
  options: {}

FetchedItem
  id
  source_id
  source_type
  title
  url
  author
  published_at
  fetched_at
  digest
  content_text
  content_markdown
  metadata
```

这样 `Horizon` 不需要进入 `name2fakeid.json`，而是进入 `external_sources.json` 或后续的 `sources.json`。

## 3. 标准化内容池

公众号文章、GitHub 动态、B 站视频、播客节目和 RSS 文章最终都要进入统一内容池，后面的去重、标签、摘要、生成才不用关心来源。

当前路径：

- 短期：公众号通过 `message_info.json` 同步进 `data/content_items.jsonl`，GitHub / B 站 / 播客等外部信源通过连接器直接同步进同一个内容池。
- 中期：保留 `data/content_items.jsonl` 作为跨来源统一内容池。
- 长期：前端从统一内容池读取，再按 `source_type`、`source_id`、标签、主题筛选。

建议标准字段：

```text
id
source_type
source_id
source_name
title
url
published_at
fetched_at
summary
tags
score
content_hash
dedupe_key
status
content_markdown
references
human_decision
feedback_notes
```

## 4. 知识沉淀层

这层负责把“信息流”变成“可复用知识”。

已经存在的低摩擦路径是：

```text
message_info.json + message_detail_text.json
  -> src/llm_wiki_bridge/export_sources.py
  -> data/llm_wiki/wechat_oa/raw/sources/wechat/**/*.md
```

后续应扩展为：

```text
content_items
  -> raw/sources/<source_type>/<source_id>/**/*.md
  -> wiki/sources
  -> wiki/entities
  -> wiki/concepts
  -> wiki/synthesis
```

知识库层要保留来源链路，任何生成内容都能追溯到原文、发布时间和采集来源。

## 5. 内容生成层

生成不是单篇文章摘要，也不是 AI 自动决定写什么。它应该从人的“话题意图”开始，再基于知识库输出多种可编辑草稿。

优先做四类：

- 每日简报：今天最值得看的内容，按主题聚合。
- 主题复盘：围绕某个关键词或赛道，把多篇来源合成一篇分析。
- 公众号草稿：标题、开头、正文结构、引用来源、结尾观点。
- 分发短内容：朋友圈、小红书、X/Threads、飞书群摘要。

生成输入应包含：

- 人指定的信息源范围：哪些账号、仓库、RSS、手动收藏参与本次生成。
- 选题目标：要解释什么问题。
- 受众：给自己看、给社群看、给公众号读者看。
- 立场与语气：观察、判断、教程、复盘、批判或推荐。
- 来源集合：必须列出可追溯 source 文件或 URL。
- 输出格式：日报、长文、短帖、卡片、邮件。

生成输出不应该直接发布，而应该进入“草稿工作台”：人可以采纳、改写、退回、要求补充来源或换角度。

## 6. 分发层

分发要先支持低风险渠道，再接需要账号权限的平台。

当前已有：

- 本地 Web 阅读界面。
- Markdown 导出目录。
- llm_wiki raw sources。

建议顺序：

1. 本地 Markdown / HTML：用于人工校对。
2. GitHub Pages：发布公开日报或知识库索引。
3. 飞书 / Slack / Discord Webhook：把日报推到工作流。
4. 邮件 Newsletter：沉淀订阅关系。
5. 微信公众号草稿箱：最后接，需要更严格的人工审核。

## 7. 人机反馈调优层

闭环的关键是人和 AI 一起反馈调优，不然系统只是自动抓取和自动写作。

反馈信号包括：

- 阅读：已读、收藏、删除、隐藏源。
- 质量：哪些来源经常产出高价值内容，哪些来源经常是广告或低质重复。
- 生成：哪些标题、结构、选题被采用，哪些被人改掉，为什么改。
- 分发：打开、点击、转发、评论。
- 人工备注：这篇为什么值得写、为什么不写、下次应该避开什么。

这些信号应该反过来影响：

- 信息源权重。
- 标签和评分策略。
- 日报入选阈值。
- 内容生成模板。
- 后续选题建议。

最小反馈数据结构应包含：

```text
item_id
event
human_decision
feedback_note
suggested_action
created_at
```

其中 `human_decision` 是闭环核心，例如：`adopted`、`rejected`、`rewrite`、`dig_deeper`、`not_relevant`。AI 可以根据这些信号生成下一轮建议，但最终是否调整来源和话题仍由人决定。

## Horizon 的接入位置

`Thysrael/Horizon` 不建议作为公众号加入，而适合作为两个层面的参考和来源：

1. 作为信息源：新增 `github_repo` 适配器，按配置抓 `Horizon` 的 releases、README、docs 或 repo activity。
2. 作为架构参考：借鉴它的多源配置、打分、去重、摘要和分发设计，但不要把它的运行时直接塞进当前公众号爬虫。

最小可行接入：

```text
data/external_sources.json
  -> github_repo:horizon
  -> bilibili_video:<bvid>
  -> podcast_feed:<rss-url>
  <- POST /api/content-loop/sources 或内容闭环页新增入口
  -> POST /api/content-loop/sync-external 或 scripts/sync_external_sources.py
  -> data/content_items.jsonl[source_type=github_repo|bilibili_video|podcast_episode]
```

如果需要知识库/调试文件，再把 snapshot 作为可选副产物：

```text
external_sources.options.snapshot_raw_sources=true
  -> data/llm_wiki/wechat_oa/raw/sources/github/horizon/*.md
  -> data/llm_wiki/wechat_oa/raw/sources/bilibili/<source_id>/*.md
  -> data/llm_wiki/wechat_oa/raw/sources/podcast/<source_id>/*.md
```

## 下一步实现顺序

1. 维护 `data/external_sources.json`，用 `type` 区分 `github_repo`、`bilibili_video`、`podcast_feed`；B 站和播客可由内容闭环页或 `POST /api/content-loop/sources` 新增。
2. 用 `POST /api/content-loop/sync-external` 或 `scripts/sync_external_sources.py --source-id <id>` 同步外部信源到 `content_items.jsonl`。
3. 对视频/播客优先使用官方字幕或 shownotes；没有文本时再启用小米 Omni 等云端 ASR provider。
4. 把可选 raw snapshot 与主信源同步分离，不要长期依赖 `message_info.json` 或 raw 文件承载所有来源。
5. 在前端新增来源类型筛选，区分公众号、GitHub、B 站、播客、RSS、手动收藏。
6. 增加内容生成脚本：从 sources 中选题、聚合、生成日报或公众号草稿。
7. 把阅读、收藏、删除、草稿采纳、人工备注和发布结果写回反馈数据，形成下一轮评分、选题和模板调整依据。

## 设计原则

- 源适配器独立：新增来源不应该改动公众号爬虫主逻辑。
- 数据模型统一：不同来源进入同一个内容池后再做生成。
- 原文可追溯：所有生成内容保留来源 URL 或 source 文件路径。
- 人是控制面：信息源、话题、角度、发布和调优都由人确定，AI 做放大和候选生成。
- 草稿优先：发布前先生成草稿和摘要，不默认全自动发到外部平台。
- 先本地可控，再外部分发：避免一开始就引入过多账号、权限和平台风险。
