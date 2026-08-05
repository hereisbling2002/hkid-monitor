# 🪪 HKID 身份证预约配额监控

> 实时监控香港六大人事登记办事处智能身份证预约配额，放号即时邮件通知。
> 第三方公益工具，非入境处官方服务。

[![GitHub Pages](https://img.shields.io/badge/demo-GitHub%20Pages-blue)](https://你的用户名.github.io/hkid-monitor/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PWA Ready](https://img.shields.io/badge/PWA-ready-5a0fc8)]()

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| 📍 **六办事处全覆盖** | 湾仔、长沙湾、将军澳、火炭、屯门、元朗 |
| ⚡ **实时监控** | ~2 分钟检测频率，秒级发现放号 |
| 📧 **邮件即时通知** | QQ SMTP 国内直连，分级提醒（🚨紧急/🔔提醒/📋常规） |
| 📱 **PWA 可安装** | 添加到手机主屏幕，像原生 App 一样使用 |
| 📡 **离线可用** | Service Worker 缓存，网络断开也能查看最后数据 |
| 💰 **零成本运行** | GitHub Actions + GitHub Pages 完全免费 |
| 🔒 **零服务器** | 无需购买或维护任何服务器 |
| 🎨 **暗色主题** | 手机优先设计，护眼暗色配色 |

## 🏗 架构

```
cron-job.org (每 2 分钟触发)
    │
    ▼
GitHub Actions (workflow)
    │
    ├─► Python 抓取脚本
    │     ├─ 请求入境处公开配额接口
    │     ├─ Diff 比对上一轮快照 → 检测新放号
    │     ├─ 更新 data/quotas.json + data/timeline.json
    │     └─ 邮件通知 (QQ SMTP)
    │
    ▼
GitHub Pages (静态站点)
    │
    ├─► index.html (PWA 看板)
    │     ├─ Service Worker (离线缓存)
    │     ├─ Web App Manifest (可安装到桌面)
    │     └─ 90 秒自动刷新
    │
    └─► 数据展示 (六办事处卡片 + 放号时间线 + 统计面板)
```

## 🚀 快速部署（6 步）

### 前置准备

- GitHub 账号
- QQ 邮箱（用于发送通知邮件）
- 本地已安装 Python 3.8+

### 步骤 1：Fork 仓库

点击右上角 **Fork** 按钮，将此仓库复制到你的账户下。

### 步骤 2：启用 GitHub Actions

进入你的仓库 → **Actions** 标签 → 点击绿色按钮 **"I understand my workflows, go ahead and enable them"**。

### 步骤 3：启用 GitHub Pages

进入 **Settings → Pages**：
- Source: `Deploy from a branch`
- Branch: `main`，目录选择 `/ (root)`
- 保存

几分钟后，看板即可访问：
```
https://你的用户名.github.io/hkid-monitor/
```

### 步骤 4：配置 Secrets

进入 **Settings → Secrets and variables → Actions → New repository secret**，添加以下 4 个密钥：

| Secret 名称 | 内容 | 获取方式 |
|---|---|---|
| `QQ_SMTP_USER` | 你的 QQ 邮箱地址 | 例如 `123456789@qq.com` |
| `QQ_SMTP_PASS` | QQ 邮箱 SMTP 授权码 | QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 开启 → 获取授权码 |
| `ADMIN_EMAIL` | 接收通知的邮箱 | 可以和 `QQ_SMTP_USER` 相同 |
| `FEISHU_WEBHOOK` | （可选）飞书群机器人 Webhook | 飞书群设置 → 群机器人 → 添加自定义机器人 |

> **获取 QQ SMTP 授权码**：登录 QQ 邮箱 → 设置 → 账户 → 找到 "POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务" → 开启 "SMTP 服务" → 按提示发送短信 → 获得 16 位授权码。

### 步骤 5：配置 2 分钟定时触发

GitHub Actions 自带的最小调度间隔是 5 分钟。要实现 2 分钟级监控，需要外部触发：

1. 注册 [cron-job.org](https://cron-job.org)（免费）
2. 创建 Cron Job：
   - **URL**: `https://api.github.com/repos/你的用户名/hkid-monitor/dispatches`
   - **Method**: `POST`
   - **Headers**: 
     - `Accept`: `application/vnd.github+json`
     - `Authorization`: `Bearer ghp_你的GitHubToken`
     - `Content-Type`: `application/json`
   - **Body**: `{"event_type": "quota-check"}`
   - **Schedule**: 每 2 分钟（`*/2 * * * *`）
3. **GitHub Token 生成**：GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → 勾选 `repository_dispatch` 权限

> 不配置此步骤也可以：系统会自动走每 15 分钟的兜底调度，只是频率低一些。

### 步骤 6：修改看板配置

编辑仓库根目录的 `config.json`：

```json
{
  "monitor": {
    "monitor_before": "2026-12-31",
    "urgent_before": "2026-09-01",
    "notice_before": "2026-10-15",
    "cooldown_minutes": 10
  }
}
```

| 参数 | 含义 |
|------|------|
| `monitor_before` | 只监控此日期前的名额（过滤远期噪声） |
| `urgent_before` | 早于此日期 → 🚨 紧急通知 |
| `notice_before` | 早于此日期 → 🔔 提醒通知 |
| `cooldown_minutes` | 同一办事处+日期的冷却时间（防重复推送） |

## 📱 PWA 使用

### 安装到手机

1. **iPhone / iPad**：Safari 浏览器打开看板 → 点击底部分享按钮 → "添加到主屏幕"
2. **Android**：Chrome 浏览器打开看板 → 点击右上角菜单 → "添加到主屏幕" / "安装应用"

### 离线使用

安装后即使没有网络也能查看最后一次缓存的配额数据。网络恢复后自动更新。

### 更新提示

当看板有新版本时，PWA 会自动提示更新。

## 📁 项目结构

```
hkid-monitor/
├── .github/workflows/monitor.yml   # GitHub Actions 工作流
├── quota_monitor/                   # Python 监控包
│   ├── __init__.py
│   ├── run.py                       # 主入口（编排流水线）
│   ├── fetcher.py                   # 抓取入境处配额接口
│   ├── differ.py                    # Diff 比对检测放号
│   ├── notifier.py                  # QQ SMTP 邮件通知
│   └── config.py                    # 配置读取与提醒分级
├── data/                            # 配额快照（自动生成）
│   ├── quotas.json                  # 最新配额数据
│   └── timeline.json                # 放号事件时间线
├── index.html                       # PWA 看板主页
├── manifest.json                    # PWA 应用清单
├── sw.js                            # Service Worker
├── config.json                      # 用户配置
├── requirements.txt                 # Python 依赖
└── README.md                        # 本文件
```

## 🔧 本地开发

```bash
# 克隆仓库
git clone https://github.com/你的用户名/hkid-monitor.git
cd hkid-monitor

# 安装依赖
pip install -r requirements.txt

# 本地运行一次抓取（不会发送邮件，除非设置环境变量）
python -m quota_monitor.run

# 本地预览看板
python -m http.server 8080
# 浏览器打开 http://localhost:8080
```

## ⚠️ 注意事项

1. **非官方服务**：数据来自入境处公开配额接口，非官方 API，接口可能随时变动
2. **仅做监控**：本项目只做监控提醒，不做代抢代约，请通过官方渠道完成预约
3. **邮件限额**：QQ 个人邮箱日发信上限约 500 封，如需大规模订阅请换企业邮箱
4. **请求频率**：请勿将监控间隔设得过低（< 1 分钟），避免对入境处服务器造成负担
5. **内地访问**：GitHub Pages 在中国大陆访问可能不稳定，建议：
   - 使用邮件订阅 + 安装 PWA 到手机（安装后部分资源由 Service Worker 缓存）
   - 可将仓库镜像到 Gitee 并开启 Gitee Pages

## 📄 许可

MIT License — 详见 [LICENSE](LICENSE) 文件

---

**参考项目**：[chen1111-a/hkid-quota-monitor](https://github.com/chen1111-a/hkid-quota-monitor) — 感谢原作者提供的架构思路
