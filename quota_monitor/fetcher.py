"""抓取入境处公开配额接口

API 来源: eservices.es2.immd.gov.hk/surgecontrolgate/ticket/getSituation?svcId=579
响应: 576 行数据 = 6 办事处 × 96 天，包含 quotaR（一般时段）和 quotaK（延长时段）
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

import requests

from .config import ROOT

logger = logging.getLogger(__name__)

# ---- 入境处真实配额查询 API ----
# 逆向自官方配额预览页: eservices.es2.immd.gov.hk/es/quota-enquiry-client/?appId=579
# 无需 Cookie / Token，直接 GET 即可
API_URL = "https://eservices.es2.immd.gov.hk/surgecontrolgate/ticket/getSituation"
API_SVC_ID = "579"

# 办事处映射: API officeId → 内部代号
OFFICE_MAP = {
    "RHK": "湾仔",
    "RKO": "长沙湾",
    "RTK": "将军澳",
    "FTO": "火炭",
    "TMO": "屯门",
    "YLO": "元朗",
}

OFFICE_NAMES_EN = {
    "RHK": "Wan Chai",
    "RKO": "Cheung Sha Wan",
    "RTK": "Tseung Kwan O",
    "FTO": "Fo Tan",
    "TMO": "Tuen Mun",
    "YLO": "Yuen Long",
}

# 状态转换: API CSS class → 单字符（参照 hkid-quota-monitor 规范）
STATUS_MAP = {
    "quota-g": "g",  # 充足
    "quota-y": "y",  # 少量
    "quota-r": "r",  # 已满
}

STATUS_LABEL = {
    "g": "充足",
    "y": "少量",
    "r": "已满",
    "x": "不开放",
}

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://eservices.es2.immd.gov.hk/es/quota-enquiry-client/?appId=579",
}

HKT = timezone(timedelta(hours=8))


def fetch_all_offices() -> dict:
    """
    抓取所有办事处的配额数据（单次请求获取全部 6 个办事处）。

    返回格式:
    {
        "fetched_at": "2026-08-05T14:30:00+08:00",
        "last_update_time": "08/05/2026 14:25:00",
        "offices": {
            "RHK": {
                "name_zh": "湾仔",
                "name_en": "Wan Chai",
                "quota": {
                    "2026-08-10": {"R": "g", "K": "x"},
                    "2026-08-11": {"R": "r", "K": "r"},
                }
            },
            ...
        }
    }
    """
    result = {
        "fetched_at": datetime.now(HKT).isoformat(),
        "offices": {},
    }

    try:
        # 构造 URL（带毫秒时间戳防缓存）
        ts = int(time.time() * 1000)
        url = f"{API_URL}?svcId={API_SVC_ID}&t={ts}"

        logger.info(f"请求 API: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=30)

        if resp.status_code != 200:
            logger.error(f"API 返回 HTTP {resp.status_code}")
            return result

        data = resp.json()
        logger.info(f"API 响应大小: {len(resp.content)} bytes")

        # 记录官方数据更新时间
        last_update = data.get("lastUpdateTime", "")
        if last_update:
            result["last_update_time"] = last_update
            logger.info(f"官方数据更新时间: {last_update}")

        # 解析 data[] 数组
        rows = data.get("data", [])
        logger.info(f"总行数: {len(rows)}")

        # 按办事处分组
        for row in rows:
            office_id = row.get("officeId", "")
            if office_id not in OFFICE_MAP:
                continue

            if office_id not in result["offices"]:
                result["offices"][office_id] = {
                    "name_zh": OFFICE_MAP[office_id],
                    "name_en": OFFICE_NAMES_EN.get(office_id, office_id),
                    "quota": {},
                }

            # 日期转换: MM/DD/YYYY → YYYY-MM-DD
            raw_date = row.get("date", "")
            try:
                dt = datetime.strptime(raw_date, "%m/%d/%Y")
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                logger.warning(f"无法解析日期: {raw_date}")
                continue

            # 解析状态
            quota_r = row.get("quotaR", "")
            quota_k = row.get("quotaK", "")

            r_status = STATUS_MAP.get(quota_r, "?")
            # quotaK 特殊处理: "no-quotaK" 表示该日无延长时段
            if quota_k == "no-quotaK":
                k_status = "x"
            else:
                k_status = STATUS_MAP.get(quota_k, "?")

            result["offices"][office_id]["quota"][date_str] = {
                "R": r_status,
                "K": k_status,
            }

        # 统计
        for oid, odata in result["offices"].items():
            q = odata["quota"]
            available = sum(1 for v in q.values() if v["R"] in ("g", "y"))
            logger.info(f"  {odata['name_zh']} ({oid}): {len(q)} 天, {available} 天可预约")

    except requests.RequestException as e:
        logger.error(f"API 请求失败: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
    except Exception as e:
        logger.error(f"未知错误: {e}")

    return result


def save_snapshot(data: dict):
    """将配额快照保存到 data/ 目录"""
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # 保存最新快照
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
