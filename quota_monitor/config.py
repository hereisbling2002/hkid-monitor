"""读取 config.json 配置"""

import json
import os
from pathlib import Path
from datetime import date


# 项目根目录（仓库根）
ROOT = Path(__file__).resolve().parent.parent

# 默认值
DEFAULTS = {
    "monitor": {
        "monitor_before": "2026-12-31",
        "urgent_before": "2026-09-01",
        "notice_before": "2026-10-15",
        "cooldown_minutes": 10,
    }
}


def load_config():
    """加载 config.json，缺失键用默认值补齐"""
    cfg = DEFAULTS.copy()

    config_path = ROOT / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        # 深度合并
        for section in user_cfg:
            if section in cfg and isinstance(cfg[section], dict):
                cfg[section].update(user_cfg[section])
            else:
                cfg[section] = user_cfg[section]

    return cfg


def get_alert_level(slot_date_str: str, cfg: dict) -> str:
    """根据日期判断提醒级别: urgent / notice / regular / ignore"""
    m = cfg.get("monitor", {})
    monitor_before = m.get("monitor_before", "2026-12-31")
    urgent_before = m.get("urgent_before", "2026-09-01")
    notice_before = m.get("notice_before", "2026-10-15")

    try:
        slot_date = date.fromisoformat(slot_date_str)
        if slot_date >= date.fromisoformat(monitor_before):
            return "ignore"
        if slot_date < date.fromisoformat(urgent_before):
            return "urgent"
        if slot_date < date.fromisoformat(notice_before):
            return "notice"
        return "regular"
    except (ValueError, TypeError):
        return "regular"
