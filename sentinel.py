"""
本地哨兵 — 每 30 秒检测一次，比 GitHub Actions 快 10 倍

用法: python sentinel.py
停止: Ctrl + C
"""

import json
import os
import smtplib
import sys
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

HKT = timezone(timedelta(hours=8))

# ---- 配置 ----
API_URL = "https://eservices.es2.immd.gov.hk/surgecontrolgate/ticket/getSituation?svcId=579"
CHECK_INTERVAL = 30  # 秒

URGENT_BEFORE = "2026-09-10"
NOTICE_BEFORE = "2026-10-15"

OFFICES = {
    "RHK": "湾仔", "RKO": "长沙湾", "RTK": "将军澳",
    "FTO": "火炭", "TMO": "屯门", "YLO": "元朗",
}

STATUS_LABEL = {"g": "充足", "y": "少量", "r": "已满", "x": "不开放"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept": "application/json",
    "Accept-Language": "zh-HK,zh;q=0.9",
    "Referer": "https://eservices.es2.immd.gov.hk/es/quota-enquiry-client/?appId=579",
}

# 邮件配置（从环境变量读取）
SMTP_CONFIG = {
    "host": "smtp.qq.com",
    "port": 587,
    "user": os.environ.get("QQ_SMTP_USER", ""),
    "password": os.environ.get("QQ_SMTP_PASS", ""),
    "to": os.environ.get("ADMIN_EMAIL", os.environ.get("QQ_SMTP_USER", "")),
}


def fetch_quotas():
    """抓取最新配额"""
    ts = int(time.time() * 1000)
    url = f"{API_URL}&t={ts}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    data = resp.json()

    quotas = {}
    for row in data.get("data", []):
        oid = row.get("officeId", "")
        if oid not in OFFICES:
            continue
        raw_date = row.get("date", "")
        try:
            dt = datetime.strptime(raw_date, "%m/%d/%Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

        qr = row.get("quotaR", "")
        qk = row.get("quotaK", "")

        r_stat = "g" if qr == "quota-g" else ("y" if qr == "quota-y" else "r")
        k_stat = "g" if qk == "quota-g" else ("y" if qk == "quota-y" else ("r" if qk == "quota-r" else "x"))

        if oid not in quotas:
            quotas[oid] = {}
        quotas[oid][date_str] = {"R": r_stat, "K": k_stat}

    last_update = data.get("lastUpdateTime", "")
    return quotas, last_update


def compare(old_q, new_q):
    """比较两轮数据，返回变化事件"""
    events = []
    for oid in OFFICES:
        old_office = old_q.get(oid, {})
        new_office = new_q.get(oid, {})
        for date_str, new_statuses in new_office.items():
            old_statuses = old_office.get(date_str, {})
            for session in ("R", "K"):
                old_s = old_statuses.get(session, "r")
                new_s = new_statuses.get(session, "r")
                # 从已满变可约
                if old_s == "r" and new_s in ("g", "y"):
                    level = _get_level(date_str)
                    events.append({
                        "office": oid, "name": OFFICES[oid],
                        "date": date_str, "session": session,
                        "new_status": new_s, "level": level,
                    })
    return events


def _get_level(date_str):
    if date_str < URGENT_BEFORE:
        return "urgent"
    elif date_str < NOTICE_BEFORE:
        return "notice"
    return "regular"


def send_email(events):
    """发送邮件通知"""
    if not SMTP_CONFIG["user"] or not SMTP_CONFIG["password"]:
        print("  ⚠️ 未配置 SMTP，跳过邮件")
        return

    highest = "urgent" if any(e["level"] == "urgent" for e in events) else \
              "notice" if any(e["level"] == "notice" for e in events) else "regular"

    icons = {"urgent": "🚨", "notice": "🔔", "regular": "📋"}
    icon = icons.get(highest, "📋")

    lines = [f"<tr><td>{icon}</td><td>{e['name']}</td><td>{e['date']}</td><td>{STATUS_LABEL.get(e['new_status'], e['new_status'])}</td></tr>" for e in events]
    rows = "\n".join(lines)

    html = f"""<!DOCTYPE html><html lang="zh-HK"><head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, sans-serif; padding: 20px; background: #f1f5f9;">
<div style="max-width: 520px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
<div style="background: {'#dc2626' if highest == 'urgent' else '#f59e0b' if highest == 'notice' else '#3b82f6'}; padding: 18px 24px; text-align: center;">
<h2 style="color: #fff; margin: 0; font-size: 18px;">{icon} HKID 放号通知</h2>
<p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 13px;">{len(events)} 个变化 · {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
<div style="padding: 24px;">
<table style="width: 100%; border-collapse: collapse; font-size: 14px;">
<tr style="background: #f8fafc;"><th style="padding: 8px 12px; text-align: left;">‼️</th><th style="text-align: left;">办事处</th><th style="text-align: left;">日期</th><th style="text-align: left;">状态</th></tr>
{rows}
</table>
<div style="margin-top: 24px; text-align: center;">
<a href="https://www.gov.hk/sc/apps/immdicbooking2.htm" style="display: inline-block; padding: 12px 32px; background: {'#dc2626' if highest == 'urgent' else '#f59e0b' if highest == 'notice' else '#3b82f6'}; color: #fff; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">立即前往预约 →</a>
</div>
</div>
</div>
</body></html>"""

    subject = f"{icon} HKID 放号 — {', '.join(list(set(e['name'] for e in events))[:3])}"
    if highest == "urgent":
        subject = "🚨 [紧急] " + subject.replace("🚨 ", "")

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_CONFIG["user"]
    msg["To"] = SMTP_CONFIG["to"]
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=15) as s:
        s.starttls()
        s.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])
        s.sendmail(SMTP_CONFIG["user"], SMTP_CONFIG["to"], msg.as_string())

    print(f"  ✅ 邮件已发送: {subject}")


def main():
    print("=" * 50)
    print("🪪  HKID 本地哨兵启动")
    print(f"⏱  检测间隔: {CHECK_INTERVAL} 秒")
    print(f"🚨 紧急线:   {URGENT_BEFORE}")
    print(f"📧 邮件:     {'已配置' if SMTP_CONFIG['user'] else '未配置'}")
    print(f"⏹  按 Ctrl+C 停止")
    print("=" * 50)

    previous = {}

    while True:
        now = datetime.now(HKT).strftime("%H:%M:%S")
        try:
            quotas, last_update = fetch_quotas()
            total_available = sum(
                1 for o in quotas.values()
                for v in o.values() if v["R"] in ("g", "y")
            )

            if previous:
                events = compare(previous, quotas)
                if events:
                    print(f"\n{'='*50}")
                    for e in events:
                        print(f"  {'🚨' if e['level']=='urgent' else '🔔'} {e['name']} {e['date']} → {STATUS_LABEL[e['new_status']]} ({e['level']})")
                    print(f"{'='*50}")
                    send_email(events)
                    print()
                else:
                    print(f"[{now}] 无变化  |  可预约: {total_available} 天  |  官方更新: {last_update}", end="\r")
            else:
                print(f"[{now}] 首次快照 |  可预约: {total_available} 天  |  官方更新: {last_update}")

            previous = quotas

        except KeyboardInterrupt:
            print(f"\n\n👋 哨兵已停止 — 共运行了 {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S')}")
            break
        except Exception as e:
            print(f"\n[{now}] ❌ 错误: {e}")
            print("  将在下次间隔后重试...")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
