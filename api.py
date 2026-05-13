#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
轻量 FastAPI 后端，供前端管理公众号列表使用。

整体职责：
  1. 账号管理  ：搜索 / 添加 / 删除公众号（读写 name2fakeid.json）
  2. 爬取任务  ：在后台线程遍历所有公众号，爬取近一月文章并写入 message_info.json；新文章会拉取正文写入 message_detail_text.json；若配置 QWEN35_27B_ENDPOINT 则调用大模型为新文章生成 tags 并写回
  3. 缓存清理  ：删除超过指定天数的旧文章记录及对应封面图、详情缓存
  4. 凭证管理  ：检测 token/cookie 是否有效；支持扫码重新登录
  5. 日志记录  ：将重要操作写入 operation_logs.jsonl，供前端日志页查看
"""

import json
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 数据目录和文件路径 ──────────────────────────────────────────────────────────
# 所有持久化数据都存放在项目根目录的 data/ 文件夹下
DATA_DIR          = Path(__file__).parent / "data"
NAME2FAKEID_FILE  = DATA_DIR / "name2fakeid.json"   # 公众号名称 → fakeid 的映射
MESSAGE_INFO_FILE = DATA_DIR / "message_info.json"  # 每个公众号的文章列表
COVERS_DIR        = DATA_DIR / "covers"             # 封面图存放目录（{article_id}.jpg）
LOGS_FILE         = DATA_DIR / "operation_logs.jsonl"  # 操作日志（每行一条 JSON）
SCHEDULE_FILE     = DATA_DIR / "crawl_schedule.json"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_schedule_state()
    _ensure_scheduler_job()
    _scheduler.start()
    try:
        yield
    finally:
        _scheduler.shutdown(wait=False)


# ── FastAPI 应用初始化 ──────────────────────────────────────────────────────────
app = FastAPI(title="微信公众号聚合 API", version="1.0.0", lifespan=lifespan)

# 允许前端开发服务器（端口 5173）跨域调用本后端（端口 8000）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 数据文件读写工具 ────────────────────────────────────────────────────────────
# 这几个函数封装了对 JSON 文件的直接读写，每次调用都会从磁盘读取最新内容，
# 避免内存中的旧数据影响结果。

def _read_name2fakeid() -> dict[str, str]:
    """读取公众号名称→fakeid 映射，文件不存在时返回空字典。"""
    if not NAME2FAKEID_FILE.exists():
        return {}
    with open(NAME2FAKEID_FILE, encoding="utf-8") as f:
        return json.load(f)


def _write_name2fakeid(data: dict[str, str]) -> None:
    """将公众号名称→fakeid 映射写回磁盘（格式化 JSON，方便人工查看）。"""
    with open(NAME2FAKEID_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _read_message_info() -> dict:
    """读取全部公众号的文章信息，文件不存在时返回空字典。"""
    if not MESSAGE_INFO_FILE.exists():
        return {}
    with open(MESSAGE_INFO_FILE, encoding="utf-8") as f:
        return json.load(f)


def _read_schedule_file() -> dict:
    """读取定时爬取配置，文件不存在时返回空字典。"""
    if not SCHEDULE_FILE.exists():
        return {}
    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _write_schedule_file(data: dict) -> None:
    """将定时爬取配置写回磁盘。"""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
_schedule_state = {
    "enabled": False,
    "time": "08:30",
    "last_run_at": "",
    "last_status": "idle",
    "last_message": "",
}


def _load_schedule_state() -> None:
    data = _read_schedule_file()
    if not data:
        return
    _schedule_state.update({
        "enabled": bool(data.get("enabled", False)),
        "time": str(data.get("time", "08:30")) or "08:30",
        "last_run_at": str(data.get("last_run_at", "")),
        "last_status": str(data.get("last_status", "idle")) or "idle",
        "last_message": str(data.get("last_message", "")),
    })


def _persist_schedule_state() -> None:
    _write_schedule_file(dict(_schedule_state))


def _scheduled_crawl_job() -> None:
    if not _schedule_state["enabled"]:
        return
    _schedule_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if _crawl_state["running"]:
        _schedule_state["last_status"] = "skipped"
        _schedule_state["last_message"] = "上一次爬取仍在进行中，本次跳过"
        _persist_schedule_state()
        return
    _schedule_state["last_status"] = "running"
    _schedule_state["last_message"] = "已触发定时爬取"
    _persist_schedule_state()
    try:
        _run_crawl()
        if _crawl_state["errors"]:
            _schedule_state["last_status"] = "error"
            _schedule_state["last_message"] = f"定时爬取完成，但有 {len(_crawl_state['errors'])} 个错误"
        else:
            _schedule_state["last_status"] = "success"
            _schedule_state["last_message"] = f"定时爬取完成，新增 {_crawl_state['new_articles']} 篇文章"
    except Exception as e:
        _schedule_state["last_status"] = "error"
        _schedule_state["last_message"] = f"定时爬取异常：{e}"
    finally:
        _persist_schedule_state()


def _ensure_scheduler_job() -> None:
    if _scheduler.get_job("daily-crawl"):
        _scheduler.remove_job("daily-crawl")
    if not _schedule_state["enabled"]:
        return
    hour_str, minute_str = _schedule_state["time"].split(":")
    _scheduler.add_job(
        _scheduled_crawl_job,
        trigger="cron",
        hour=int(hour_str),
        minute=int(minute_str),
        id="daily-crawl",
        replace_existing=True,
    )

class SearchRequest(BaseModel):
    """前端搜索公众号时传入的请求体。"""
    query: str  # 搜索关键词（公众号名称）


class SearchCandidate(BaseModel):
    """搜索结果中单个公众号候选项。"""
    fakeid: str        # 微信内部 ID，用于后续爬取
    nickname: str      # 公众号名称
    alias: str         # 微信号（英文 ID，可能为空）
    avatar: str        # 头像图片 URL（round_head_img）
    signature: str     # 简介
    service_type: int  # 0=订阅号, 1=服务号, 2=其他


class ConfirmAddRequest(BaseModel):
    """用户从搜索结果中选定后，确认添加时传入的请求体。"""
    name: str    # 用户确认使用的名称（即 nickname）
    fakeid: str  # 从搜索结果中选定的 fakeid


class AccountStatus(BaseModel):
    """单个公众号的状态摘要，供前端列表展示。"""
    name: str
    fakeid: str
    has_articles: bool      # 是否已有爬取到的文章
    article_count: int      # 当前有效文章数（已删除的不计）
    latest_update_time: str # 最后一次成功爬取的时间


class CrawlStatus(BaseModel):
    """爬取任务的实时进度，前端通过轮询获取。"""
    running: bool
    total: int
    done: int
    current: str
    errors: list[str]
    started_at: str
    finished_at: str
    new_articles: int
    auth_error: bool = False


class CrawlScheduleStatus(BaseModel):
    enabled: bool
    time: str
    last_run_at: str
    last_status: str
    last_message: str


class CrawlScheduleUpdate(BaseModel):
    enabled: bool
    time: str


class WikiExportResult(BaseModel):
    """llm_wiki source 导出结果。"""
    export_root: str
    raw_sources_dir: str
    exported: int
    skipped: int
    accounts: int


class ExternalSyncRequest(BaseModel):
    """同步外部信源的请求体。"""
    config_path: str | None = None
    export_root: str | None = None
    use_example: bool = True
    source_ids: list[str] | None = None


ExternalImportRequest = ExternalSyncRequest


class ExternalSourceUpsertRequest(BaseModel):
    """新增或更新 B 站视频 / 播客 RSS 信源。"""
    url: str
    source_type: str = "auto"
    name: str = ""
    human_reason: str = ""
    transcribe: bool = True
    enabled: bool = True
    sync_now: bool = True
    tags: list[str] | None = None


class FeedbackEventRequest(BaseModel):
    """人的判断/反馈，写回闭环数据层。"""
    item_id: str
    event: str = "item_reviewed"
    human_decision: str
    feedback_note: str = ""
    suggested_action: str = ""
    channel: str = "local_web"
    weight: float = 1.0


class TaggingRequest(BaseModel):
    """批量打标签请求。默认使用 data/tag_taxonomy.json 或 example 词表。"""
    taxonomy_path: str | None = None


class AIEnrichRequest(BaseModel):
    """批量 AI 分类与摘要。默认只处理尚未生成 AI 摘要的内容。"""
    limit: int = 30
    only_missing: bool = True
    source_type: str | None = None
    tag: str | None = None
    item_ids: list[str] | None = None
    max_chars: int = 3200


# ── 日志系统 ────────────────────────────────────────────────────────────────────

_log_lock = threading.Lock()

# 日志类型常量，对应前端日志页中的图标和颜色
LOG_CRAWL_START    = "crawl_start"
LOG_CRAWL_FINISH   = "crawl_finish"
LOG_CRAWL_ERROR    = "crawl_error"
LOG_ACCOUNT_ADD    = "account_add"
LOG_ACCOUNT_REMOVE = "account_remove"
LOG_CACHE_CLEAR    = "cache_clear"
LOG_ARTICLE_DELETE = "article_delete"
LOG_COVER_REFILL   = "cover_refill"
LOG_WIKI_EXPORT = "wiki_export"
LOG_CONTENT_SYNC = "content_sync"
LOG_EXTERNAL_SYNC = "external_sync"
LOG_EXTERNAL_IMPORT = LOG_EXTERNAL_SYNC
LOG_EXTERNAL_SOURCE_ADD = "external_source_add"
LOG_FEEDBACK_EVENT = "feedback_event"
LOG_TAGGING_RUN = "tagging_run"
LOG_AI_ENRICH = "ai_enrich"


def _append_log(log_type: str, message: str, details: dict | None = None) -> None:
    """
    向 data/operation_logs.jsonl 追加一条日志（线程安全）。

    每条日志格式：
      {"timestamp": "...", "type": "crawl_start", "message": "...", "details": {...}}
    """
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": log_type,
        "message": message,
        "details": details or {},
    }
    with _log_lock:
        # 确保目录存在（初次运行时 data/ 可能还没有）
        LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOGS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 工具函数 ────────────────────────────────────────────────────────────────────

# 下载封面图时使用的 HTTP 请求头，模拟浏览器访问，避免微信服务器拒绝请求
_DOWNLOAD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
    'Referer': 'https://mp.weixin.qq.com/',
}


def _download_cover(article_id: str, cover_url: str) -> None:
    """
    下载单篇文章的封面图，保存到 data/covers/{article_id}.jpg。

    处理逻辑：
    - 文件已存在则跳过（幂等，重复爬取不会重复下载）
    - 图片宽度超过 640px 时等比缩放，节省磁盘空间
    - RGBA/P 模式（带透明通道的 PNG）转为 RGB 再保存为 JPEG
    - 下载失败只打印警告，不影响主流程
    """
    if not cover_url:
        return
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    # article_id 中可能含 "/" 字符，替换为 "_" 以兼容文件名
    filename = article_id.replace("/", "_") + ".jpg"
    dest = COVERS_DIR / filename
    if dest.exists():
        return  # 已下载过，跳过
    try:
        import io
        import requests
        from PIL import Image

        resp = requests.get(cover_url, timeout=15, headers=_DOWNLOAD_HEADERS)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        # JPEG 不支持透明通道，先转为 RGB
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        width, height = img.size
        if width > 640:
            new_height = int(height * 640.0 / width)
            img = img.resize((640, new_height), Image.Resampling.LANCZOS)
        img.save(dest, "JPEG", quality=85)
    except Exception as e:
        print(f"[cover] 下载失败 {article_id}: {e}")


def _fetch_article_detail_text(article_id: str, link: str) -> bool:
    """
    根据文章链接拉取 HTML 正文（url2text），写入 data_manager.message_detail_text。

    存储格式与 deduplication / blog_generator 一致：正常为段落 list[str]；
    url2text 在文章删除、请求失败时可能返回 str（如「已删除」「请求错误」），原样写入。

    若该 article_id 在 message_detail_text 中已存在则跳过，避免重复抓取。
    返回 True 表示本次写入了新数据，需要随后 write("message_detail_text")。
    """
    if not link or not article_id:
        return False
    from src.utils.data_manager import data_manager
    from src.utils.helpers import url2text

    if article_id in data_manager.message_detail_text:
        return False

    try:
        text = url2text(link)
        data_manager.message_detail_text[article_id] = text
        return True
    except Exception as e:
        print(f"[detail] 抓取正文失败 {article_id}: {e}")
        return False


def _get_wechat():
    """
    初始化 WechatRequest 实例（会读取 data/id_info.json 中的 token/cookie）。
    初始化失败时抛出 503 错误，统一在调用处感知。
    """
    try:
        from src import WechatRequest
        return WechatRequest()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"初始化微信请求失败：{e}，请确认 data/id_info.json 有效")


# ── 账号管理 API ────────────────────────────────────────────────────────────────

@app.get("/api/accounts", response_model=list[AccountStatus])
def list_accounts():
    """
    返回所有已添加的公众号及其状态。

    数据来源：
    - name2fakeid.json  → 已添加的公众号列表
    - message_info.json → 各公众号的文章数量和最后更新时间
    """
    name2fakeid = _read_name2fakeid()
    message_info = _read_message_info()

    result = []
    for name, fakeid in name2fakeid.items():
        entry = message_info.get(name, {})
        blogs = entry.get("blogs", [])
        # 过滤掉已被微信删除的文章
        active_blogs = [b for b in blogs if not b.get("is_deleted", False)]
        result.append(
            AccountStatus(
                name=name,
                fakeid=fakeid,
                has_articles=len(active_blogs) > 0,
                article_count=len(active_blogs),
                latest_update_time=entry.get("latest_update_time", ""),
            )
        )
    return result


@app.post("/api/accounts/search", response_model=list[SearchCandidate])
def search_accounts(body: SearchRequest):
    """
    在微信公众平台搜索公众号，返回候选列表（最多 5 条）。

    这是添加公众号的第一步：前端展示候选列表，用户选择后再调用
    POST /api/accounts 确认添加。此接口不修改任何本地数据。
    """
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空")

    # 先验证 id_info.json 是否有效，失败时直接抛 503，避免后续无效请求
    _get_wechat()
    try:
        import requests as req
        from src.utils.data_manager import data_manager, headers as wechat_headers

        # 复制全局 headers 并注入当前 Cookie
        h = dict(wechat_headers)
        h['Cookie'] = data_manager.id_info['cookie']
        params = {
            'action': 'search_biz',
            'begin': 0,
            'count': 5,
            'query': query,
            'token': data_manager.id_info['token'],
            'lang': 'zh_CN',
            'f': 'json',
            'ajax': 1,
        }
        response = req.get(
            'https://mp.weixin.qq.com/cgi-bin/searchbiz?',
            params=params,
            headers=h,
            timeout=15,
        ).json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"微信接口请求失败：{e}")

    # 微信接口正常时 ret=0，非 0 表示 token/cookie 问题
    if response.get('base_resp', {}).get('ret') != 0:
        raise HTTPException(
            status_code=502,
            detail=f"微信接口返回错误：{response.get('base_resp', {}).get('err_msg', '未知')}，请检查 token/cookie 是否过期",
        )

    # 将微信返回的字段映射到前端友好的结构
    candidates = []
    for item in response.get('list', []):
        candidates.append(SearchCandidate(
            fakeid=item.get('fakeid', ''),
            nickname=item.get('nickname', ''),
            alias=item.get('alias', ''),
            avatar=item.get('round_head_img', ''),
            signature=item.get('signature', ''),
            service_type=item.get('service_type', 0),
        ))
    return candidates


@app.post("/api/accounts", response_model=AccountStatus, status_code=201)
def add_account(body: ConfirmAddRequest):
    """
    确认添加公众号：将用户选定的 name + fakeid 写入 name2fakeid.json。

    调用时机：前端搜索并展示候选后，用户点击"确认添加"触发。
    重复添加同名公众号会返回 409 冲突错误。
    """
    name = body.name.strip()
    fakeid = body.fakeid.strip()
    if not name or not fakeid:
        raise HTTPException(status_code=400, detail="name 和 fakeid 不能为空")

    name2fakeid = _read_name2fakeid()
    if name in name2fakeid:
        raise HTTPException(status_code=409, detail=f"公众号「{name}」已在列表中")

    name2fakeid[name] = fakeid
    _write_name2fakeid(name2fakeid)

    # 记录操作日志
    _append_log(LOG_ACCOUNT_ADD, f"添加公众号「{name}」", {"name": name, "fakeid": fakeid})

    # 新添加的公众号没有文章，返回初始状态
    return AccountStatus(
        name=name,
        fakeid=fakeid,
        has_articles=False,
        article_count=0,
        latest_update_time="",
    )


@app.delete("/api/accounts/{name}", status_code=204)
def remove_account(name: str):
    """
    从跟踪列表中移除公众号（只删除 name2fakeid.json 中的记录，
    不删除已爬取的文章数据，如需清理可使用缓存清理功能）。
    """
    name2fakeid = _read_name2fakeid()
    if name not in name2fakeid:
        raise HTTPException(status_code=404, detail=f"公众号「{name}」不在列表中")

    del name2fakeid[name]
    _write_name2fakeid(name2fakeid)
    _append_log(LOG_ACCOUNT_REMOVE, f"移除公众号「{name}」", {"name": name})


# ── 删除单篇文章 ────────────────────────────────────────────────────────────────

class ArticleDeleteRequest(BaseModel):
    """从前端移除一篇文章：写入黑名单并删除本地记录。"""
    article_id: str   # 文章唯一 id（msgid-aid-create_time）
    account: str      # 所属公众号名称（message_info 的 key）


@app.post("/api/articles/remove")
def remove_article(body: ArticleDeleteRequest):
    """
    将文章 id 写入 data/deleted_article_ids.json，并从 message_info 中移除该条。
    后续爬取时若微信仍返回该文，会因 id 在黑名单中而跳过。
    同时尝试删除本地封面与详情缓存。
    """
    from src.utils.data_manager import data_manager

    aid = body.article_id.strip()
    acc = body.account.strip()
    if not aid or not acc:
        raise HTTPException(status_code=400, detail="article_id 和 account 不能为空")

    data_manager.reload("deleted_article_ids")
    data_manager.reload("message_info")

    if acc not in data_manager.message_info:
        raise HTTPException(status_code=404, detail=f"公众号「{acc}」不存在")

    blogs = data_manager.message_info[acc].get("blogs", [])
    if not any(b.get("id") == aid for b in blogs):
        raise HTTPException(status_code=404, detail="文章不存在或已删除")

    # 黑名单
    raw = data_manager.deleted_article_ids
    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="deleted_article_ids.json 格式异常，请检查 data 目录")
    if "ids" not in raw or not isinstance(raw["ids"], list):
        raw["ids"] = []
    ids_list: list = raw["ids"]
    if aid not in ids_list:
        ids_list.append(aid)
    data_manager.write("deleted_article_ids")

    # 从 message_info 移除
    data_manager.message_info[acc]["blogs"] = [b for b in blogs if b.get("id") != aid]
    data_manager.write("message_info")

    # 本地封面
    cover_path = COVERS_DIR / (aid.replace("/", "_") + ".jpg")
    if cover_path.exists():
        try:
            cover_path.unlink()
        except OSError:
            pass

    # 详情缓存
    detail_file = DATA_DIR / "message_detail_text.json"
    if detail_file.exists():
        try:
            with open(detail_file, encoding="utf-8") as f:
                detail_texts = json.load(f)
            if aid in detail_texts:
                del detail_texts[aid]
                with open(detail_file, "w", encoding="utf-8") as f:
                    json.dump(detail_texts, f, ensure_ascii=False, indent=4)
            data_manager.reload("message_detail_text")
        except (json.JSONDecodeError, OSError):
            pass

    _append_log(
        LOG_ARTICLE_DELETE,
        f"删除文章「{aid}」（{acc}）",
        {"article_id": aid, "account": acc},
    )

    return {"ok": True, "article_id": aid}


# ── 凭证状态（内存缓存） ─────────────────────────────────────────────────────────
# _auth_state 在进程内存中记录最近一次凭证检测结果。
# 程序重启后重置为初始值（valid=True 表示"尚未验证"）。
# 这个状态会在以下时机被更新：
#   - 每次爬取成功/失败时
#   - 调用 /api/auth/check 主动检测时
#   - 扫码登录完成时

_auth_state: dict = {
    "valid": True,    # 凭证是否有效（True 也可能是"尚未检测"的默认值）
    "checked_at": "", # 上次检测时间（空字符串表示本次启动后尚未检测）
    "error": "",      # 失败原因，如 "invalid csrf token"
}


def _mark_auth_failed(reason: str) -> None:
    """标记凭证失效，记录失败原因和时间。"""
    _auth_state["valid"] = False
    _auth_state["checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _auth_state["error"] = reason


def _mark_auth_ok() -> None:
    """标记凭证有效，清除之前的错误信息。"""
    _auth_state["valid"] = True
    _auth_state["checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _auth_state["error"] = ""


# ── 爬取任务 ────────────────────────────────────────────────────────────────────
# 爬取在后台线程中运行，前端通过轮询 /api/crawl/status 获取进度。
# _crawl_state 是共享状态，由后台线程写、API 线程读，
# 读写较简单（Python GIL 保护），暂不加锁。

_crawl_state: dict = {
    "running": False,      # 是否有爬取任务正在运行
    "total": 0,            # 本次需要处理的公众号总数
    "done": 0,             # 已处理完的公众号数（成功+失败）
    "current": "",         # 当前正在处理的公众号名称
    "errors": [],          # 本次爬取中出现的所有错误
    "started_at": "",      # 任务开始时间
    "finished_at": "",     # 任务结束时间（运行中为空）
    "new_articles": 0,     # 本次新增文章总数
    "auth_error": False,   # True = 因凭证失效提前终止（不是普通错误）
}
_crawl_lock = threading.Lock()  # 仅用于防止并发启动两个爬取任务

# 微信 API 返回这些 err_msg 时说明 token/cookie 已失效
_AUTH_FAIL_MSGS = {"invalid session", "invalid csrf token", "csrf token invalid"}


def _check_auth_valid() -> tuple[str, str]:
    """
    向微信 API 发送一次轻量探测请求，检测 token/cookie 是否有效。

    返回：(status, reason)
      - status="ok", reason=""                  → 凭证正常
      - status="auth_invalid", reason="..."    → 凭证失效
      - status="transport_error", reason="..." → 网络传输异常
    """
    import requests
    from src.utils.data_manager import data_manager

    id_info = data_manager.id_info
    token = id_info.get("token", "").strip()
    cookie = id_info.get("cookie", "").strip()
    if not token or not cookie:
        return "auth_invalid", "id_info.json 中 token 或 cookie 为空"

    headers = dict(_DOWNLOAD_HEADERS)
    headers["Cookie"] = cookie
    params = {
        "action": "search_biz",
        "begin": 0,
        "count": 1,
        "query": "test",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1,
    }

    session = requests.Session()
    session.trust_env = False

    try:
        resp = session.get(
            "https://mp.weixin.qq.com/cgi-bin/searchbiz?",
            params=params,
            headers=headers,
            timeout=10,
        ).json()
    except Exception as e:
        return "transport_error", f"检测时出现网络异常: {e}"

    err_msg = resp.get("base_resp", {}).get("err_msg", "ok")
    if err_msg in _AUTH_FAIL_MSGS:
        return "auth_invalid", f"凭证已失效（{err_msg}）"
    return "ok", ""


def _run_crawl() -> None:
    """
    后台爬取线程的主函数，流程如下：

    1. 立即更新 _crawl_state.total，让前端第一次轮询就能看到账号总数
    2. 从磁盘重新加载最新凭证（data_manager.reload），支持手动更新 id_info.json
    3. 调用 _check_auth_valid() 做预检：凭证失效时立刻终止，不逐个账号重试
    4. 遍历所有公众号，调用 WechatRequest.fakeid2message_update() 获取新文章
    5. 对每篇新文章下载封面图、拉正文；可选 LLM 打标签后写入 message_info.json
    6. 每处理完一个公众号（成功或失败），done += 1
    7. 全部完成后写入结束日志，设置 running=False
    """
    global _crawl_state

    try:
        # ── 第一步：立即更新 total，让前端尽快看到正确的进度分母 ──
        quick_n2f = _read_name2fakeid()
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _crawl_state.update({
            "running": True,
            "total": len(quick_n2f),
            "done": 0,
            "current": "",
            "errors": [],
            "started_at": started_at,
            "finished_at": "",
            "new_articles": 0,
            "auth_error": False,
        })

        from src.crawler.wechat_request import WechatRequest
        from src.llm.article_summary import summarize_article
        from src.llm.article_tagging import tag_article
        from src.utils.data_manager import data_manager
        from src.utils.helpers import time_now

        # ── 第二步：从磁盘重新加载，确保内存数据是最新的 ──
        # 特别是 id_info，用户可能在服务运行时手动修改了 token/cookie
        data_manager.reload("id_info")
        data_manager.reload("name2fakeid")
        data_manager.reload("message_info")
        data_manager.reload("issues_message")
        data_manager.reload("deleted_article_ids")
        data_manager.reload("message_detail_text")

        # ── 第三步：凭证预检 ──────────────────────────────────────────
        # 如果凭证已失效，提前终止，避免每个账号都等待超时再报错
        auth_status, auth_reason = _check_auth_valid()
        if auth_status == "auth_invalid":
            _crawl_state["auth_error"] = True
            _crawl_state["errors"].append(f"凭证失效，已终止爬取：{auth_reason}")
            _mark_auth_failed(auth_reason)
            _append_log(LOG_CRAWL_ERROR, f"凭证失效，爬取终止：{auth_reason}", {"reason": auth_reason})
            return
        if auth_status == "transport_error":
            warning = f"预检网络异常，继续尝试爬取：{auth_reason}"
            _crawl_state["errors"].append(warning)
            _append_log(LOG_CRAWL_ERROR, warning, {"reason": auth_reason, "stage": "auth_precheck"})

        name2fakeid: dict[str, str] = dict(data_manager.name2fakeid)
        # reload 后账号数可能与 quick_n2f 不同，更新 total 保持一致
        _crawl_state["total"] = len(name2fakeid)

        _append_log(LOG_CRAWL_START, f"开始爬取，共 {len(name2fakeid)} 个公众号",
                    {"accounts": list(name2fakeid.keys())})

        wechat = WechatRequest(auto_login=False)  # 禁止自动打开浏览器，凭证失效时抛异常
        new_total = 0  # 本次爬取新增文章的累计数

        # ── 第四步：逐个公众号爬取 ──────────────────────────────────────
        for oa_name, fakeid in name2fakeid.items():
            _crawl_state["current"] = oa_name  # 更新"正在处理"的账号名，供前端展示
            try:
                # 首次爬取该公众号时，初始化其记录结构
                if oa_name not in data_manager.message_info:
                    data_manager.message_info[oa_name] = {
                        "latest_update_time": "2000-01-01 00:00",
                        "blogs": [],
                    }

                existing_blogs: list = data_manager.message_info[oa_name]["blogs"]
                # fakeid2message_update 内部通过 article_id 去重，只返回新增文章
                new_articles = wechat.fakeid2message_update(fakeid, existing_blogs)

                if new_articles:
                    data_manager.message_info[oa_name]["blogs"].extend(new_articles)
                    new_total += len(new_articles)
                    detail_dirty = False
                    # 新文章：下载封面 + 拉取正文写入 message_detail_text.json
                    for article in new_articles:
                        _download_cover(article["id"], article.get("cover", ""))
                        if _fetch_article_detail_text(article["id"], article.get("link", "")):
                            detail_dirty = True
                    if detail_dirty:
                        data_manager.write("message_detail_text")

                    # LLM 打标签与摘要（仅当配置了 QWEN35_27B_ENDPOINT；失败不影响爬取）
                    try:
                        for article in new_articles:
                            try:
                                tags = tag_article(article, data_manager)
                                if tags:
                                    article["tags"] = tags
                                summary = summarize_article(article, data_manager)
                                if summary:
                                    article["summary"] = summary
                            except Exception as e:
                                print(f"[llm] 单篇处理失败 {article.get('id')}: {e}")
                    except Exception as e:
                        print(f"[llm] 处理模块异常: {e}")

                # 更新最后爬取时间
                data_manager.message_info[oa_name]["latest_update_time"] = time_now()
                data_manager.write("message_info")

                # 爬取成功 → 凭证有效，更新状态
                _mark_auth_ok()

            except Exception as e:
                err_str = str(e)
                err_msg = f"{oa_name}: {err_str}"
                _crawl_state["errors"].append(err_msg)
                _append_log(LOG_CRAWL_ERROR, f"爬取「{oa_name}」失败：{e}",
                            {"account": oa_name, "error": err_str})
                # 判断是否是凭证失效导致的错误（微信 API 返回的特定错误字符串）
                if any(kw in err_str.lower() for kw in ("invalid session", "invalid csrf", "csrf token", "session")):
                    _mark_auth_failed(err_str)
            finally:
                # 无论成功还是失败，都算处理完一个，done + 1
                _crawl_state["done"] += 1
                _crawl_state["new_articles"] = new_total

    except Exception as e:
        # 初始化阶段（循环外）出现的异常
        err_str = str(e)
        _crawl_state["errors"].append(f"初始化失败: {err_str}")
        _append_log(LOG_CRAWL_ERROR, f"爬取初始化失败：{e}", {"error": err_str})
        if any(kw in err_str.lower() for kw in ("invalid session", "invalid csrf", "csrf token", "cookie", "token")):
            _mark_auth_failed(err_str)
    finally:
        # 无论正常结束还是抛出异常，都要更新结束状态
        finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _crawl_state["current"] = ""
        _crawl_state["finished_at"] = finished_at
        _crawl_state["running"] = False
        errors = _crawl_state["errors"]
        _append_log(
            LOG_CRAWL_FINISH,
            f"爬取完成：新增 {_crawl_state['new_articles']} 篇，"
            f"共 {_crawl_state['total']} 个公众号，{len(errors)} 个错误",
            {
                "new_articles": _crawl_state["new_articles"],
                "total_accounts": _crawl_state["total"],
                "errors": errors,
                "started_at": _crawl_state.get("started_at", ""),
                "finished_at": finished_at,
            },
        )


@app.post("/api/crawl")
def start_crawl():
    """
    启动后台爬取任务。
    同一时间只允许一个爬取任务运行，重复调用返回 409 冲突。
    """
    with _crawl_lock:
        if _crawl_state["running"]:
            raise HTTPException(status_code=409, detail="爬取任务正在进行中，请等待完成后再试")
        # daemon=True：主进程退出时后台线程自动终止，不会阻止程序退出
        t = threading.Thread(target=_run_crawl, daemon=True)
        t.start()
    return {"status": "started", "message": "爬取任务已开始"}



@app.get("/api/crawl/schedule", response_model=CrawlScheduleStatus)
def get_crawl_schedule():
    return CrawlScheduleStatus(**_schedule_state)


@app.post("/api/crawl/schedule", response_model=CrawlScheduleStatus)
def update_crawl_schedule(body: CrawlScheduleUpdate):
    time_str = body.time.strip()
    if len(time_str) != 5 or time_str[2] != ":":
        raise HTTPException(status_code=400, detail="时间格式必须为 HH:MM")
    hour_str, minute_str = time_str.split(":")
    try:
        hour = int(hour_str)
        minute = int(minute_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式必须为 HH:MM")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="时间必须落在 00:00 到 23:59 之间")

    _schedule_state["enabled"] = body.enabled
    _schedule_state["time"] = f"{hour:02d}:{minute:02d}"
    if body.enabled:
        _schedule_state["last_status"] = _schedule_state.get("last_status") or "idle"
        _schedule_state["last_message"] = _schedule_state.get("last_message") or "已启用定时爬取"
    else:
        _schedule_state["last_status"] = "disabled"
        _schedule_state["last_message"] = "已关闭定时爬取"
    _persist_schedule_state()
    _ensure_scheduler_job()
    return CrawlScheduleStatus(**_schedule_state)

@app.get("/api/crawl/status", response_model=CrawlStatus)
def get_crawl_status():
    """返回当前爬取任务的实时进度，前端每隔 800ms 轮询一次。"""
    return CrawlStatus(**_crawl_state)


@app.post("/api/wiki/export-sources", response_model=WikiExportResult)
def export_wiki_sources():
    """
    将当前已采集文章导出为 llm_wiki 兼容的 raw sources。

    这是桌面知识库分支的第一层桥接：采集仍由本项目负责，后续 ingest
    可以读取 data/llm_wiki/wechat_oa/raw/sources/wechat 下的 Markdown。
    """
    try:
        from src.llm_wiki_bridge import export_llm_wiki_sources

        result = export_llm_wiki_sources()
        _append_log(
            LOG_WIKI_EXPORT,
            f"同步 llm_wiki sources：{result.exported} 篇文章",
            result.__dict__,
        )
        return WikiExportResult(**result.__dict__)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出 llm_wiki sources 失败：{e}")


# ── 内容闭环 API ────────────────────────────────────────────────────────────────
# 这组接口把公众号缓存、外部源、统一内容池和人工反馈接起来。

@app.get("/api/content-loop/overview")
def content_loop_overview():
    """返回内容闭环当前状态：内容池、反馈、外部源配置和公众号候选素材数量。"""
    from src.content_loop import get_content_loop_overview

    return get_content_loop_overview()


@app.get("/api/content-loop/items")
def content_loop_items(
    limit: int = 100,
    source_type: str | None = None,
    tag: str | None = None,
    human_decision: str | None = None,
):
    """返回统一内容池中的最近条目，默认不返回完整正文，避免前端加载过重。"""
    from src.content_loop import list_content_items

    return list_content_items(
        limit=limit,
        source_type=source_type or None,
        tag=tag or None,
        human_decision=human_decision or None,
    )


@app.get("/api/sources")
def list_unified_sources_api():
    """聚合公众号和外部源，返回统一 Source 读模型。"""
    from src.content_loop import list_unified_sources

    return list_unified_sources()


@app.get("/api/content-loop/sources")
def content_loop_sources():
    """返回外部源配置；若 data/external_sources.json 不存在，会展示 example 方便首次接入。"""
    from src.content_loop import load_external_source_configs

    return load_external_source_configs(allow_example=True)


@app.post("/api/content-loop/sources")
def content_loop_upsert_source(body: ExternalSourceUpsertRequest):
    """新增或更新 B 站视频 / 播客 RSS 信源，可立即同步到统一内容池。"""
    from src.content_loop import SourceConfigError

    try:
        from src.content_loop import sync_external_sources, upsert_media_source_config

        result = upsert_media_source_config(
            url=body.url,
            source_type=body.source_type,
            name=body.name,
            human_reason=body.human_reason,
            transcribe=body.transcribe,
            tags=body.tags,
            enabled=body.enabled,
        )
        sync_result = None
        if body.sync_now and body.enabled:
            sync_result = sync_external_sources(
                config_path=Path(result["config_path"]),
                source_ids=[result["source"]["id"]],
                use_example=False,
            )
        payload = {**result, "sync_result": sync_result}
        action = "新增" if result["created"] else "更新"
        synced = int((sync_result or {}).get("items_synced") or 0)
        errors = (sync_result or {}).get("errors") or []
        _append_log(
            LOG_EXTERNAL_SOURCE_ADD,
            f"{action}外部信源：{result['source']['name']}，同步 {synced} 条，错误 {len(errors)} 个",
            payload,
        )
        return payload
    except SourceConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存外部信源失败：{e}")


@app.get("/api/content-loop/tags")
def content_loop_tags():
    """返回标签词表、标签覆盖率和当前内容池里的标签分布。"""
    from src.content_loop import get_tagging_overview

    return get_tagging_overview()


@app.post("/api/content-loop/tagging")
def content_loop_tagging(body: TaggingRequest):
    """按本地标签词表给 content_items.jsonl 批量打标签，并生成 topic_tags.jsonl。"""
    try:
        from src.content_loop import apply_tags_to_content_items

        result = apply_tags_to_content_items(
            taxonomy_path=Path(body.taxonomy_path) if body.taxonomy_path else None,
        )
        payload = result.__dict__
        _append_log(
            LOG_TAGGING_RUN,
            f"内容池打标签：{payload['tagged']}/{payload['total']} 条已覆盖",
            payload,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内容打标签失败：{e}")


@app.get("/api/content-loop/ai-status")
def content_loop_ai_status():
    """返回 AI 分类/摘要配置状态，不返回 API key 明文。"""
    from src.content_loop import get_ai_enrichment_overview

    return get_ai_enrichment_overview()


@app.post("/api/content-loop/ai-enrich")
def content_loop_ai_enrich(body: AIEnrichRequest):
    """使用配置好的 OpenAI-compatible 模型为内容池生成 AI 摘要与分类。"""
    if body.limit < 1:
        raise HTTPException(status_code=400, detail="limit 必须 >= 1")
    if body.max_chars < 500:
        raise HTTPException(status_code=400, detail="max_chars 必须 >= 500")
    try:
        from src.content_loop import ai_enrich_content_items

        result = ai_enrich_content_items(
            limit=body.limit,
            only_missing=body.only_missing,
            source_type=body.source_type,
            tag=body.tag,
            item_ids=body.item_ids,
            max_chars=body.max_chars,
        )
        payload = result.__dict__
        _append_log(
            LOG_AI_ENRICH,
            f"AI 分类总结：处理 {payload['processed']} 条，失败 {payload['failed']} 条",
            {k: v for k, v in payload.items() if k != "errors"},
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 分类总结失败：{e}")


@app.post("/api/content-loop/sync-wechat")
def content_loop_sync_wechat():
    """
    将现有 message_info/message_detail_text 标准化写入 data/content_items.jsonl。

    这是从公众号单一数据模型迁移到多源 ContentItem 池的兼容入口。
    """
    try:
        from src.content_loop import sync_wechat_content_items

        result = sync_wechat_content_items()
        _append_log(
            LOG_CONTENT_SYNC,
            f"同步公众号内容池：标准化 {result['normalized']} 条，当前总计 {result['total']} 条",
            result,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步内容池失败：{e}")


@app.post("/api/content-loop/sync-external")
def content_loop_sync_external(body: ExternalSyncRequest):
    """按 data/external_sources.json 中启用的连接器同步外部信源，并写入 content_items。"""
    try:
        from src.content_loop import sync_external_sources

        result = sync_external_sources(
            config_path=Path(body.config_path) if body.config_path else None,
            export_root=Path(body.export_root) if body.export_root else None,
            use_example=body.use_example,
            source_ids=body.source_ids,
        )
        _append_log(
            LOG_EXTERNAL_SYNC,
            f"同步外部信源：{result['items_synced']} 条内容，{len(result['errors'])} 个错误",
            result,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步外部信源失败：{e}")


@app.post("/api/sources/{source_id}/sync")
def sync_unified_source(source_id: str):
    """按统一 Source 读模型触发单个信源同步。"""
    source_key = source_id.strip()
    if not source_key:
        raise HTTPException(status_code=400, detail="source_id 不能为空")

    if source_key.startswith("wechat:"):
        account_name = source_key.split(":", 1)[1]
        if not account_name:
            raise HTTPException(status_code=400, detail="无效的公众号 source_id")
        try:
            from src.content_loop import sync_wechat_content_items

            result = sync_wechat_content_items()
            _append_log(
                LOG_CONTENT_SYNC,
                f"同步公众号内容池（单源入口）：{account_name}，标准化 {result['normalized']} 条，当前总计 {result['total']} 条",
                {**result, "source_id": source_key, "source_name": account_name},
            )
            return {"source_id": source_key, "source_name": account_name, "source_type": "wechat_account", "result": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"同步公众号失败：{e}")

    try:
        from src.content_loop import sync_external_sources

        result = sync_external_sources(use_example=False, source_ids=[source_key])
        _append_log(
            LOG_EXTERNAL_SYNC,
            f"同步单个外部信源：{source_key}，{result['items_synced']} 条内容，{len(result['errors'])} 个错误",
            {**result, "source_id": source_key},
        )
        return {"source_id": source_key, "source_type": "external_source", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步外部信源失败：{e}")


@app.post("/api/content-loop/feedback")
def content_loop_feedback(body: FeedbackEventRequest):
    """将人的采纳、改写、继续深挖、不相关等判断写入 feedback_events.jsonl。"""
    item_id = body.item_id.strip()
    decision = body.human_decision.strip()
    if not item_id or not decision:
        raise HTTPException(status_code=400, detail="item_id 和 human_decision 不能为空")

    try:
        from src.content_loop import record_feedback_event

        result = record_feedback_event(
            item_id=item_id,
            event=body.event.strip() or "item_reviewed",
            human_decision=decision,
            feedback_note=body.feedback_note.strip(),
            suggested_action=body.suggested_action.strip(),
            channel=body.channel.strip() or "local_web",
            weight=body.weight,
        )
        _append_log(
            LOG_FEEDBACK_EVENT,
            f"记录人工反馈：{decision} / {item_id}",
            result["event"],
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录反馈失败：{e}")


# ── 缓存清理 ─────────────────────────────────────────────────────────────────────
# 随着爬取积累，message_info.json 和封面图会越来越多。
# 这组接口允许用户按"保留最近 N 天"的策略清理旧数据。

class CachePreview(BaseModel):
    """清理预览结果，让用户在执行前看到将删除的数量。"""
    keep_days: int
    cutoff_date: str          # 截止日期（此日期之前的文章会被删除）
    total_articles: int       # 当前全部文章数
    removable_articles: int   # 将被删除的文章数
    removable_covers: int     # 将被删除的封面图数
    removable_detail_texts: int  # 将被删除的详情缓存数


class CacheClearRequest(BaseModel):
    """清理请求，指定要保留的天数。"""
    keep_days: int = 90


class CacheClearResult(BaseModel):
    """清理结果，返回实际删除的数量。"""
    removed_articles: int
    removed_covers: int
    removed_detail_texts: int


def _collect_removable_ids(keep_days: int) -> tuple[str, set[str]]:
    """
    计算哪些文章 ID 需要被删除。

    返回 (cutoff_date_str, set_of_removable_ids)：
    - cutoff_date_str：截止日期字符串（格式 "YYYY-MM-DD HH:MM"）
    - set_of_removable_ids：所有早于截止日期的文章 ID 集合
    """
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M")
    message_info = _read_message_info()
    removable: set[str] = set()
    for account in message_info.values():
        for blog in account.get("blogs", []):
            if blog.get("create_time", "9999") < cutoff:
                removable.add(blog["id"])
    return cutoff, removable


@app.get("/api/cache/preview", response_model=CachePreview)
def cache_preview(keep_days: int = 90):
    """
    预览清理结果：统计将被删除的文章数、封面图数、详情缓存数。
    不执行任何实际删除，只供前端展示确认弹窗。
    """
    if keep_days < 1:
        raise HTTPException(status_code=400, detail="keep_days 必须 >= 1")

    cutoff, removable_ids = _collect_removable_ids(keep_days)
    message_info = _read_message_info()
    total_articles = sum(len(v.get("blogs", [])) for v in message_info.values())

    # 统计可删除的封面图（按文件名匹配）
    removable_covers = 0
    if COVERS_DIR.exists():
        cover_files = {f.stem: f for f in COVERS_DIR.glob("*.jpg")}
        for rid in removable_ids:
            if rid.replace("/", "_") in cover_files:
                removable_covers += 1

    # 统计可删除的详情缓存（message_detail_text.json 中的键）
    detail_text_file = DATA_DIR / "message_detail_text.json"
    removable_detail_texts = 0
    if detail_text_file.exists():
        with open(detail_text_file, encoding="utf-8") as f:
            detail_texts: dict = json.load(f)
        removable_detail_texts = sum(1 for rid in removable_ids if rid in detail_texts)

    return CachePreview(
        keep_days=keep_days,
        cutoff_date=cutoff[:10],
        total_articles=total_articles,
        removable_articles=len(removable_ids),
        removable_covers=removable_covers,
        removable_detail_texts=removable_detail_texts,
    )


@app.post("/api/cache/clear", response_model=CacheClearResult)
def clear_cache(body: CacheClearRequest):
    """
    执行缓存清理，删除早于 keep_days 天的数据：
      1. 从 message_info.json 删除旧文章记录
      2. 从 data/covers/ 删除对应封面图文件
      3. 从 message_detail_text.json 删除对应详情缓存
      4. 刷新 data_manager 内存，避免旧数据残留

    爬取任务运行期间禁止清理，以避免数据写入冲突。
    """
    if _crawl_state["running"]:
        raise HTTPException(status_code=409, detail="爬取任务正在进行中，请等待完成后再清理")
    if body.keep_days < 1:
        raise HTTPException(status_code=400, detail="keep_days 必须 >= 1")

    _, removable_ids = _collect_removable_ids(body.keep_days)
    if not removable_ids:
        return CacheClearResult(removed_articles=0, removed_covers=0, removed_detail_texts=0)

    # 1. 从 message_info.json 移除旧文章
    message_info = _read_message_info()
    for account in message_info.values():
        account["blogs"] = [b for b in account.get("blogs", []) if b["id"] not in removable_ids]
    with open(MESSAGE_INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(message_info, f, ensure_ascii=False, indent=4)

    # 2. 删除封面图文件
    removed_covers = 0
    if COVERS_DIR.exists():
        for rid in removable_ids:
            cover_path = COVERS_DIR / (rid.replace("/", "_") + ".jpg")
            if cover_path.exists():
                cover_path.unlink()
                removed_covers += 1

    # 3. 从 message_detail_text.json 删除详情缓存
    removed_detail_texts = 0
    detail_text_file = DATA_DIR / "message_detail_text.json"
    if detail_text_file.exists():
        with open(detail_text_file, encoding="utf-8") as f:
            detail_texts: dict = json.load(f)
        before = len(detail_texts)
        detail_texts = {k: v for k, v in detail_texts.items() if k not in removable_ids}
        removed_detail_texts = before - len(detail_texts)
        with open(detail_text_file, "w", encoding="utf-8") as f:
            json.dump(detail_texts, f, ensure_ascii=False, indent=4)

    # 4. 同步刷新 data_manager 内存，避免旧数据在本次进程中继续存在
    try:
        from src.utils.data_manager import data_manager
        data_manager.reload("message_info")
        data_manager.reload("message_detail_text")
    except Exception:
        pass

    _append_log(
        LOG_CACHE_CLEAR,
        f"清理缓存：删除 {len(removable_ids)} 篇文章（{body.keep_days} 天前），"
        f"封面图 {removed_covers} 张，详情缓存 {removed_detail_texts} 条",
        {
            "keep_days": body.keep_days,
            "cutoff_date": (datetime.now() - timedelta(days=body.keep_days)).strftime("%Y-%m-%d"),
            "removed_articles": len(removable_ids),
            "removed_covers": removed_covers,
            "removed_detail_texts": removed_detail_texts,
        },
    )

    return CacheClearResult(
        removed_articles=len(removable_ids),
        removed_covers=removed_covers,
        removed_detail_texts=removed_detail_texts,
    )


class CoverRefillPreview(BaseModel):
    """封面补全预览，返回缺失封面的文章数量。"""
    total_articles: int
    missing_covers: int


class CoverRefillResult(BaseModel):
    """封面补全执行结果。"""
    total_articles: int
    missing_before: int
    downloaded: int
    failed: int


def _collect_articles_missing_cover() -> tuple[int, list[dict]]:
    """收集所有缺失本地封面的有效文章。"""
    message_info = _read_message_info()
    missing: list[dict] = []
    total_articles = 0
    for account_name, account in message_info.items():
        for blog in account.get("blogs", []):
            if blog.get("is_deleted", False):
                continue
            total_articles += 1
            article_id = blog.get("id", "")
            if not article_id:
                continue
            cover_path = COVERS_DIR / (article_id.replace("/", "_") + ".jpg")
            if cover_path.exists():
                continue
            if not blog.get("cover"):
                continue
            missing.append({
                "account": account_name,
                "id": article_id,
                "title": blog.get("title", ""),
                "cover": blog.get("cover", ""),
            })
    return total_articles, missing


@app.get("/api/covers/refill/preview", response_model=CoverRefillPreview)
def cover_refill_preview():
    """预览当前缺失本地封面的文章数量。"""
    total_articles, missing = _collect_articles_missing_cover()
    return CoverRefillPreview(total_articles=total_articles, missing_covers=len(missing))


@app.post("/api/covers/refill", response_model=CoverRefillResult)
def refill_covers():
    """补下载所有缺失的本地封面图。"""
    if _crawl_state["running"]:
        raise HTTPException(status_code=409, detail="爬取任务正在进行中，请等待完成后再补全封面")

    total_articles, missing_articles = _collect_articles_missing_cover()
    if not missing_articles:
        return CoverRefillResult(total_articles=total_articles, missing_before=0, downloaded=0, failed=0)

    downloaded = 0
    failed = 0
    for article in missing_articles:
        try:
            _download_cover(article["id"], article["cover"])
            cover_path = COVERS_DIR / (article["id"].replace("/", "_") + ".jpg")
            if cover_path.exists():
                downloaded += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    _append_log(
        LOG_COVER_REFILL,
        f"封面补全：尝试 {len(missing_articles)} 篇，成功 {downloaded}，失败 {failed}",
        {
            "total_articles": total_articles,
            "missing_before": len(missing_articles),
            "downloaded": downloaded,
            "failed": failed,
        },
    )

    return CoverRefillResult(
        total_articles=total_articles,
        missing_before=len(missing_articles),
        downloaded=downloaded,
        failed=failed,
    )


# ── 日志查询 API ────────────────────────────────────────────────────────────────

class LogEntry(BaseModel):
    """单条操作日志的结构。"""
    timestamp: str
    type: str
    message: str
    details: dict


@app.get("/api/logs", response_model=list[LogEntry])
def get_logs(limit: int = 200):
    """
    返回最近 limit 条操作日志，按时间倒序（最新的在最前面）。
    日志文件为 JSONL 格式，每行一条。
    """
    if not LOGS_FILE.exists():
        return []
    with open(LOGS_FILE, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    entries = []
    # 先取最后 limit 行（最新的），再反转让最新的排在最前
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


# ── 凭证状态查询 API ────────────────────────────────────────────────────────────

class AuthStatus(BaseModel):
    """凭证状态的完整信息，供前端状态横幅展示。"""
    has_credentials: bool  # id_info.json 中是否有非空的 token 和 cookie
    valid: bool            # 上次检测/爬取是否成功（False 表示凭证失效）
    checked_at: str        # 上次检测时间（空 = 本次启动后尚未检测）
    error: str             # 失败原因（空 = 正常）
    token_hint: str        # token 前 8 位，供用户确认是否是最新的值
    id_info_mtime: str     # id_info.json 文件的最后修改时间


def _build_auth_status() -> AuthStatus:
    """
    组合内存中的 _auth_state 和磁盘上的 id_info.json 元数据，
    构建完整的 AuthStatus 对象。
    """
    id_info_file = DATA_DIR / "id_info.json"
    has_credentials = False
    token_hint = ""
    mtime = ""

    if id_info_file.exists():
        try:
            with open(id_info_file, encoding="utf-8") as f:
                info = json.load(f)
            token = info.get("token", "").strip()
            cookie = info.get("cookie", "").strip()
            has_credentials = bool(token and cookie)
            # 只展示 token 前 8 位，防止完整 token 被截图泄露
            token_hint = token[:8] + "..." if len(token) > 8 else token
            mtime = datetime.fromtimestamp(id_info_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return AuthStatus(
        has_credentials=has_credentials,
        valid=_auth_state["valid"],
        checked_at=_auth_state["checked_at"],
        error=_auth_state["error"],
        token_hint=token_hint,
        id_info_mtime=mtime,
    )


@app.get("/api/auth/status", response_model=AuthStatus)
def get_auth_status():
    """
    返回缓存的凭证状态，不发起实际微信请求。
    用于页面加载时快速展示状态，速度快但可能不是最新结果。
    """
    return _build_auth_status()


@app.post("/api/auth/check", response_model=AuthStatus)
def check_auth_now():
    """
    主动向微信 API 发起探测请求，实时验证 token/cookie 是否有效。
    用于用户手动点击"重新检测"时，会更新内存中的 _auth_state。
    调用前先从磁盘重新加载凭证，确保检测的是用户最新修改的值。
    """
    from src.utils.data_manager import data_manager
    # 先重新加载，确保使用的是用户最新修改的凭证
    data_manager.reload("id_info")

    status, reason = _check_auth_valid()
    if status == "ok":
        _mark_auth_ok()
    elif status == "auth_invalid":
        _mark_auth_failed(reason)
    else:
        _auth_state["checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _auth_state["error"] = reason

    return _build_auth_status()


# ── 扫码登录 ────────────────────────────────────────────────────────────────────
# 当凭证过期时，用户可以通过前端触发扫码登录流程：
#   1. 后端用无头 Chrome 打开微信公众平台登录页
#   2. 每 2 秒截图保存到 _login_state["qrcode_img"]
#   3. 前端轮询 /api/auth/qrcode 获取截图并展示
#   4. 用户扫码后，后端检测 URL 中出现 token，提取并保存凭证
#   5. 前端轮询 /api/auth/login/status 检测完成，关闭弹窗

_login_state: dict = {
    "running": False,    # 是否正在等待扫码
    "done": False,       # 本次登录流程是否已结束（成功或失败）
    "error": "",         # 失败时的错误信息
    "qrcode_img": "",    # 最新二维码截图（data:image/png;base64,...）
    "qrcode_at": "",     # 截图时间（"HH:MM:SS"）
    "started_at": "",    # 登录流程开始时间
    "finished_at": "",   # 登录流程结束时间
}
_login_lock = threading.Lock()  # 保护 _login_state 的多线程读写


def _run_login() -> None:
    """
    后台登录线程：
      - 用无头 Chrome 打开微信登录页面（不弹出可见窗口）
      - 循环截图，让前端可以展示二维码供用户扫描
      - 检测到 URL 含 token 后，提取 token + cookie 写入 id_info.json
      - 3 分钟内未扫码则超时退出
    """
    import os
    import re
    import time

    # 清除代理环境变量，避免本地 Chrome DevTools WebSocket 连接被代理拦截
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(_k, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    bro = None
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
        from src.utils.data_manager import data_manager

        # headless=True：不弹出可见窗口，在后台渲染页面
        # auto_port()：自动分配调试端口，避免与已有 Chrome 冲突
        co = ChromiumOptions().auto_port().headless(True)
        bro = ChromiumPage(co)
        bro.set.window.size(1280, 800)  # 设置虚拟窗口大小，影响截图分辨率
        bro.get("https://mp.weixin.qq.com/")

        # 首屏会先出现登录骨架/文案，二维码 img 晚几秒才出现；若此时截全页会误导用户。
        # 先等待二维码节点出现，再进入轮询；只推送「二维码元素」截图，不再用全页图当二维码。
        qr_wait_deadline = time.time() + 35
        qr_elem = None
        while time.time() < qr_wait_deadline and "token" not in bro.url:
            try:
                qr_elem = bro.ele("css:img[src*='qrcode']", timeout=2)
                if qr_elem:
                    break
            except Exception:
                pass
            time.sleep(0.35)
        if "token" not in bro.url and not qr_elem:
            raise Exception("页面未在预期时间内加载出登录二维码，请检查网络或稍后重试")

        # 二维码一出现就推送首帧，避免再等主循环一轮才写入 _login_state
        if qr_elem and "token" not in bro.url:
            try:
                _b64 = qr_elem.get_screenshot(as_base64=True)
                if _b64:
                    with _login_lock:
                        _login_state["qrcode_img"] = f"data:image/png;base64,{_b64}"
                        _login_state["qrcode_at"] = datetime.now().strftime("%H:%M:%S")
            except Exception:
                pass

        max_wait = 180  # 最多等待 3 分钟
        start = time.time()

        while "token" not in bro.url:
            if time.time() - start > max_wait:
                raise Exception("等待扫码超时（3 分钟），请重试")

            img_b64 = ""
            try:
                qr_elem = bro.ele("css:img[src*='qrcode']", timeout=3)
                if qr_elem:
                    img_b64 = qr_elem.get_screenshot(as_base64=True)
            except Exception:
                pass

            if img_b64:
                with _login_lock:
                    _login_state["qrcode_img"] = f"data:image/png;base64,{img_b64}"
                    _login_state["qrcode_at"] = datetime.now().strftime("%H:%M:%S")

            time.sleep(2)  # 每 2 秒刷新一次截图（二维码会过期刷新）

        # ── 扫码成功，从 URL 提取 token ──
        match = re.search(r"token=(\d+)", bro.url)
        if not match:
            raise ValueError("无法从 URL 中解析 token")
        token = match.group(1)

        # 将所有 cookie 拼接为字符串（"name=value; name2=value2; ..."）
        cookies = bro.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        # 写入 id_info.json，同时更新内存中的 data_manager
        data_manager.id_info["token"] = token
        data_manager.id_info["cookie"] = cookie_str
        data_manager.write("id_info")

        _mark_auth_ok()
        with _login_lock:
            _login_state.update(running=False, done=True, error="",
                                qrcode_img="", qrcode_at="",
                                finished_at=datetime.now().strftime("%H:%M:%S"))
    except Exception as e:
        with _login_lock:
            _login_state.update(running=False, done=True, error=str(e),
                                qrcode_img="", qrcode_at="",
                                finished_at=datetime.now().strftime("%H:%M:%S"))
    finally:
        # 无论成功还是失败，都关闭浏览器，释放资源
        try:
            if bro:
                bro.quit()
        except Exception:
            pass


class LoginStatus(BaseModel):
    """扫码登录的进度状态。"""
    running: bool
    done: bool
    error: str
    started_at: str
    finished_at: str


@app.post("/api/auth/login")
def start_login():
    """
    启动扫码登录流程（后台线程），立即返回。
    同一时间只允许一个登录流程运行。
    """
    with _login_lock:
        if _login_state["running"]:
            return {"detail": "已有登录流程正在进行，请扫描当前二维码"}
        _login_state.update(running=True, done=False, error="",
                            qrcode_img="", qrcode_at="",
                            started_at=datetime.now().strftime("%H:%M:%S"),
                            finished_at="")
    threading.Thread(target=_run_login, daemon=True).start()
    return {"detail": "正在加载登录页面，请稍候..."}


@app.get("/api/auth/login/status", response_model=LoginStatus)
def get_login_status():
    """查询当前扫码登录流程的状态，前端每 2 秒轮询一次。"""
    with _login_lock:
        return LoginStatus(**{k: _login_state[k] for k in LoginStatus.model_fields})


@app.get("/api/auth/qrcode")
def get_qrcode():
    """
    返回最新的微信登录二维码截图（base64 编码的 PNG）。
    前端每 2 秒调用一次，刷新展示的二维码图片（二维码有有效期，会自动更新）。
    """
    with _login_lock:
        img = _login_state.get("qrcode_img", "")
        at = _login_state.get("qrcode_at", "")
    if not img:
        raise HTTPException(status_code=404, detail="暂无二维码，请先点击扫码登录")
    return {"img": img, "refreshed_at": at}
