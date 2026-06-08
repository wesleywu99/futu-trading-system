# Google Cloud 部署指南

将 Futu Trading System 部署到 Google Cloud 免费层（e2-micro），运行命令行版 Futu OpenD。

**月费用：$0（永久免费）**

---

## 前置条件

- Google 账号（Gmail）
- 信用卡（验证用，不扣费）
- 富途牛牛号和登录密码

---

## 第一步：创建 GCP 虚拟机

1. 访问 [Google Cloud Console](https://console.cloud.google.com/compute/instances)
2. 如果是首次使用，需要：
   - 创建项目（如 `futu-trading`）
   - 添加信用卡（不扣费，仅验证）
3. 点击 **Create Instance**
4. 配置：

| 参数 | 值 | 备注 |
|------|-----|------|
| Name | `futu-trading` | 自定义 |
| Region | `us-central1` (Iowa) | 必须是 us-central1/us-east1/us-west1 才免费 |
| Machine type | `e2-micro` | Always Free 标记 |
| Boot disk | Ubuntu 22.04 LTS, 30 GB Standard PD | 默认即可 |
| Firewall | Allow HTTP/HTTPS | 可选 |

5. 点击 **Create**
6. 记录 VM 的 **External IP**（如 `35.222.xxx.xxx`）

### 通过 SSH 连接

在 GCP Console 中点击 VM 旁边的 SSH 按钮，或使用命令行：

```bash
gcloud compute ssh futu-trading --zone=us-central1-a
```

---

## 第二步：上传项目代码

在**本地 Windows PowerShell** 执行：

```powershell
scp -r C:\Users\decdior\futu-trading-system 你的用户名@VM外部IP:~/futu-trading-system
```

或者在 VM 上用 git clone（如果项目在 GitHub 上）。

---

## 第三步：运行部署脚本

SSH 到 VM 后，执行：

```bash
cd ~/futu-trading-system/deploy/gcp
chmod +x deploy.sh

# 方式1：用明文密码（脚本自动计算 MD5）
./deploy.sh --account 你的牛牛号 --password 你的密码

# 方式2：直接提供 MD5（更安全）
# 先在本地计算 MD5：echo -n '你的密码' | md5sum
./deploy.sh --account 你的牛牛号 --password-md5 你的密码MD5
```

脚本会自动完成：
- 安装系统依赖（Python3, git, telnet, curl）
- 创建 2GB Swap（1GB RAM 不够用）
- 下载并安装命令行版 Futu OpenD
- 配置 FutuOpenD.xml（账号密码）
- 创建 Python 虚拟环境并安装依赖
- 安装 systemd 服务（自动启动 + 崩溃重启）
- 启动 OpenD

---

## 第四步：首次登录验证

首次启动 OpenD 时，可能需要短信验证码。

### 查看日志

```bash
sudo journalctl -u futu-opend -f
```

### 输入短信验证码

当看到需要验证码的提示时：

```bash
telnet 127.0.0.1 22222
input_phone_verify_code -code=收到的验证码
```

### 输入图片验证码

如果需要图片验证码：

```bash
# 1. 从 OpenD 目录复制验证码图片
cp ~/futu-opend/F3CNN/PicVerifyCode.png /tmp/
# 2. 下载到本地查看（在本地 PowerShell 执行）
scp 你的用户名@VM外部IP:/tmp/PicVerifyCode.png .
# 3. 通过 telnet 输入验证码
telnet 127.0.0.1 22222
input_pic_verify_code -code=图片中的验证码
```

---

## 第五步：启动交易系统

确认 OpenD 登录成功后（日志显示 `login success`）：

```bash
sudo systemctl enable futu-trading
sudo systemctl start futu-trading
```

---

## 日常运维

### 查看状态

```bash
sudo systemctl status futu-opend
sudo systemctl status futu-trading
```

### 查看实时日志

```bash
# OpenD 日志
sudo journalctl -u futu-opend -f

# 交易系统日志
sudo journalctl -u futu-trading -f

# 交易日志文件
tail -f ~/futu-trading-system/logs/trading.log
```

### 重启服务

```bash
sudo systemctl restart futu-opend
sudo systemctl restart futu-trading
```

### 通过 Telnet 管理 OpenD

```bash
telnet 127.0.0.1 22222
# 可用命令：重登录、退出登录、查看状态等
```

---

## 注意事项

1. **内存**：e2-micro 只有 1GB RAM，部署脚本已自动创建 2GB Swap
2. **IP 变化**：GCP 免费层 VM 重启后 IP 可能变化。如需固定 IP：
   - VPC Network > External IP addresses > Reserve Static
   - 免费（VM 运行时），VM 停止后收费
3. **短信验证**：Futu 服务端可能定期刷新设备白名单，需要重新短信验证
4. **交易解锁**：不能通过代码调用 unlock_trade，需通过 telnet 手动操作
5. **监控**：建议开启 config.yaml 中的 Telegram 通知，方便远程监控
6. **备份**：定期备份 logs/ 目录和 config/config.yaml

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| OpenD 登录失败 | 检查账号密码，确认 MD5 正确：`echo -n '密码' \| md5sum` |
| 连接超时 | 确认 VM 网络正常，`curl -I https://www.futunn.com` |
| 内存不足 | 检查 swap：`free -h`，确保有 2GB swap |
| 服务启动失败 | 查看日志：`sudo journalctl -u futu-trading -n 50` |
| Python 模块缺失 | 激活 venv 后重新安装：`source venv/bin/activate && pip install -r requirements.txt` |

---

## 架构图

```
Google Cloud e2-micro (Ubuntu 22.04)
├── systemd: futu-opend.service
│   └── FutuOpenD (CLI) → 127.0.0.1:11111
│       └── 连接富途服务器（行情 + 交易）
├── systemd: futu-trading.service
│   └── Python (venv) → 127.0.0.1:11111
│       └── 策略引擎 → 信号 → 风控 → 下单
└── telnet: 127.0.0.1:22222
    └── OpenD 管理（验证码、重登录、状态）
```
