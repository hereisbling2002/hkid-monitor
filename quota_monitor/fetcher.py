"""抓取入境处公开配额接口"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

import requests

from .config import ROOT

logger = logging.getLogger(__name__)

# ---- 入境处配额查询 API ----
# 此接口来自入境处官网预约系统的同源 AJAX 接口
# 参考: hkid-quota-monitor/docs/api-notes.md

BASE_URL = "https://webapp.es2.immd.gov.hk/smartics2-client/ropbooking"

# 六个办事处对应的请求参数（实际参数需通过浏览器 DevTools 抓包确认）
# 以下为推断值，如接口变动需更新
OFFICES = {
    "WC":  {"code": "WCH", "name_zh": "湾仔",     "name_en": "Wan Chai"},
    "CSW": {"code": "CSW", "name_zh": "长沙湾",   "name_en": "Cheung Sha Wan"},
    "TKO": {"code": "TKO", "name_zh": "将军澳",   "name_en": "Tseung Kwan O"},
    "FT":  {"code": "FOT", "name_zh": "火炭",     "name_en": "Fo Tan"},
    "TM":  {"code": "TMN", "name_zh": "屯门",     "name_en": "Tuen Mun"},
    "YL":  {"code": "YUL", "name_zh": "元朗",     "name_en": "Yuen Long"},
}

# 请求头（模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://webapp.es2.immd.gov.hk/smartics2-client/ropbooking/",
}

HKT = timezone(timedelta(hours=8))


def fetch_all_offices() -> dict:
    """
    抓取所有办事处的配额数据。

    返回格式:
    {
        "fetched_at": "2026-08-05T14:30:00+08:00",
        "offices": {
            "WC": {"name_zh": "湾仔", "quota": {"2026-08-10": 5, "2026-08-11": 0}},
            "CSW": {...}, ...
        }
    }
    """
    result = {
        "fetched_at": datetime.now(HKT).isoformat(),
        "offices": {},
    }

    session = requests.Session()
    session.headers.update(HEADERS)

    for office_id, office_info in OFFICES.items():
        try:
            quota = _fetch_office(session, office_info["code"])
            result["offices"][office_id] = {
                "name_zh": office_info["name_zh"],
                "name_en": office_info["name_en"],
                "quota": quota,
            }
            logger.info(f"  {office_info['name_zh']}: {len(quota)} 天有数据")
            time.sleep(0.5)  # 礼貌间隔，避免请求过快
        except Exception as e:
            logger.warning(f"  {office_info['name_zh']}: 抓取失败 — {e}")
            result["offices"][office_id] = {
                "name_zh": office_info["name_zh"],
                "name_en": office_info["name_en"],
                "quota": {},
                "error": str(e),
            }

    session.close()
    return result


def _fetch_office(session: requests.Session, office_code: str) -> dict:
    """
    抓取单个办事处的配额。

    注意: 实际 API endpoint 和参数需要从入境处官网预约页面抓包确认。
    以下 URL 和参数格式为推断，需要根据实际情况调整。

    已知端点模式（参考 hkid-quota-monitor）:
    - 查询日配额: GET /api/booking/dailyQuota?officeId={code}&date={date}
    - 查询可用日期: GET /api/booking/availableDates?officeId={code}
    """
    # ---- 方式 1: 查询可用日期列表 ----
    try:
        url = f"{BASE_URL}/api/booking/availableDates"
        params = {"officeId": office_code}
        resp = session.get(url, params=params, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            return _parse_quota_response(data)

        logger.warning(f"    {office_code}: HTTP {resp.status_code}")
    except requests.RequestException as e:
        logger.warning(f"    {office_code}: 请求异常 — {e}")

    # ---- 方式 2: 回退 — 逐日查询接下来 96 个工作日 ----
    # （效率较低但更可靠）
    try:
        return _fetch_by_date_range(session, office_code)
    except Exception:
        pass

    return {}


def _parse_quota_response(data: dict) -> dict:
    """
    解析 API 响应为 {日期: 配额数} 字典。
    由于入境处 API 为非公开接口，此解析逻辑需根据实际响应结构调整。
    """
    quota = {}

    # 尝试多种可能的响应格式
    if isinstance(data, dict):
        # 格式 1: {"dates": [{"date": "2026-08-10", "quota": 5}, ...]}
        for item in data.get("dates", []):
            d = item.get("date")
            q = item.get("quota", item.get("remaining", 0))
            if d:
                quota[d] = int(q)

        # 格式 2: {"2026-08-10": 5, "2026-08-11": 0}
        if not quota:
            for k, v in data.items():
                if isinstance(k, str) and len(k) == 10 and k[4] == "-":
                    quota[k] = int(v) if isinstance(v, (int, float)) else 0

    elif isinstance(data, list):
        # 格式 3: [{"date": "2026-08-10", "quota": 5}, ...]
        for item in data:
            d = item.get("date")
            q = item.get("quota", item.get("remaining", 0))
            if d:
                quota[d] = int(q)

    return quota


def _fetch_by_date_range(session: requests.Session, office_code: str,
                         num_days: int = 96) -> dict:
    """逐日回退查询（效率低，仅在主接口失败时使用）"""
    from datetime import date as Date, timedelta

    quota = {}
    today = Date.today()

    for i in range(num_days):
        d = (today + timedelta(days=i)).isoformat()
        try:
            url = f"{BASE_URL}/api/booking/dailyQuota"
            resp = session.get(url, params={"officeId": office_code, "date": d}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                q = data.get("quota", data.get("remaining", 0))
                if isinstance(q, (int, float)):
                    quota[d] = int(q)
        except Exception:
            continue

    return quota


def save_snapshot(data: dict):
    """将配额快照保存到 data/ 目录"""
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # 保存最新的快照（会覆盖）
    snapshot_path = data_dir / "quotas.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"快照已保存: {snapshot_path}")


def load_previous_snapshot() -> dict:
    """加载上一轮快照，用于 diff 比对"""
    snapshot_path = ROOT / "data" / "quotas.json"
    if snapshot_path.exists():
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
