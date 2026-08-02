# nova 15 Pro hilog 5 种命令实测方案(V1.3 装上后用)

**目标**:V1.3 HAP 装到 nova 15 Pro 后,User 用本指南跑 5 种 hilog 命令,看能否抓到 V1.3 业务日志
**精度等级**:**沙箱实证**(2026-06-26 10:13 hdc 工具找到,真机未连)
**已知问题**(2026-06-25 06:42 失职):V1.3 装成功但 onCreate 不触发 + hilog 抓不到业务

---

## 一、hdc 工具位置(Mavis 沙箱实证)

**hdc 路径**:`C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`
**hdc 版本**:Ver: 3.2.0e(2026-06-26 沙箱实测)

---

## 二、连接 nova 15 Pro(前置 5 分钟)

### 步骤 1:USB 连接

1. 用 USB 数据线连接 nova 15 Pro 到 PC
2. 手机端下滑通知 → "USB 用途" → 选"传输文件 / MIDI"或"仅充电"
3. 手机端"设置" → "关于手机" → 连点 7 次"版本号" → 打开"开发者模式"
4. "设置" → "系统和更新" → "开发人员选项" → 打开"USB 调试"

### 步骤 2:PC 端验证连接

```powershell
# PowerShell 跑(从 hdc 目录)
cd "C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains"
.\hdc.exe list targets
```

**期望输出**:
```
69F9K25C27023877                (nova 15 Pro 序列号)
[Empty]                          (没连真机)
```

**沙箱实证(2026-06-26 10:13)**:
- 连 USB 前:`[Empty]`
- 连 USB 后:显示序列号 `69F9K25C27023877`

### 步骤 3:把 hdc 加到 PATH(可选)

**让 hilog 命令不用每次写长路径**:
1. Win+R → `sysdm.cpl` → 系统属性
2. 高级 → 环境变量
3. 系统变量 → Path → 编辑
4. 新建 → 粘贴 `C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains`
5. 确定 → 确定
6. 重启 PowerShell

---

## 三、5 种 hilog 命令实测(连真机后)

### 命令 1:hilog -T 5(最近 5 行)

```powershell
hdc hilog -T 5
```

**期望输出**:5 行系统日志(不一定是 V1.3)
**已知问题**:可能输出系统全局日志,过滤不到 V1.3

### 命令 2:hilog -x(详细模式)

```powershell
hdc hilog -x
```

**期望输出**:详细信息(时间 / 进程 ID / 标签)
**已知问题**:可能阻塞,需 Ctrl+C 退出

### 命令 3:hilog -z 30(最近 30 秒)

```powershell
hdc hilog -z 30
```

**期望输出**:30 秒内的日志
**已知问题**:可能输出大量系统日志,需 grep 过滤

### 命令 4:hilog -T 1(最近 1 行)

```powershell
hdc hilog -T 1
```

**期望输出**:1 行最新日志
**已知问题**:可能阻塞,需 Ctrl+C 退出

### 命令 5:hilog > hilog.log 2>&1 & (后台输出文件)

```powershell
hdc hilog > D:\zhishe-hilog.log 2>&1 &
```

**期望输出**:后台持续输出到文件
**已知问题**:可能不退出,需手动 kill 进程

---

## 四、V1.3 业务日志过滤(关键)

### 过滤 V1.3 包名

```powershell
# PowerShell 跑,过滤 com.zhishe.renovation.agent
hdc hilog | Select-String "com.zhishe.renovation.agent"
```

或写文件 + grep:

```powershell
# 1. 后台跑 hilog 输出文件
hdc hilog > D:\zhishe-hilog.log 2>&1

# 2. 另一窗口 grep 过滤
Get-Content D:\zhishe-hilog.log -Wait | Select-String "com.zhishe.renovation.agent"
```

### 过滤 onCreate 事件

```powershell
# 过滤 onCreate
hdc hilog | Select-String -Pattern "onCreate|RenovationConsult"
```

### 过滤 HTTP 请求

```powershell
# 过滤 HTTPS 调用
hdc hilog | Select-String "tunnel.zhishe.top|deepseek|HTTPS"
```

### 过滤异常

```powershell
# 过滤 ERROR / Exception
hdc hilog | Select-String -Pattern "ERROR|Exception|Failed"
```

---

## 五、5 大已知问题(2026-06-25 失职记录)

### 问题 1:V1.3 装上后 onCreate 不触发

**Mavis 2026-06-25 06:42 实证**:
- V1.3 装 nova 15 Pro 成功
- 启动 success
- 但 onCreate 不触发(PID 持续空)
- 智能体调用时无业务日志

**可能根因**:
- 签名问题(HAP 签名失败)
- 权限问题(ohos.permission.INTERNET 缺失)
- Intent 解析失败(zhishe://renovation/consult 无法识别)

**应急**:
- 卸载 V1.3 → 重新装
- 看 logcat 启动日志(grep "renovation")
- 联系华为开发者支持

### 问题 2:hilog 阻塞不退出

**问题**:`hdc hilog` 命令卡住,Ctrl+C 才能退出
**应急**:
- `hdc hilog -T 1` 看最近 1 行(快)
- `hdc hilog -z 5` 看最近 5 秒(快)
- 用 `> file &` 后台跑

### 问题 3:输出系统全局日志,过滤不到 V1.3

**问题**:hilog 输出几 MB 系统日志,grep 不到 V1.3
**应急**:
- 用 `> file` 输出到文件,grep 过滤
- 用 `hdc hilog -T 1 | grep "com.zhishe"`
- **Mavis 推:用 `> file &` 后台跑 → grep "com.zhishe.renovation.agent"**

### 问题 4:nova 15 Pro 没连 USB

**问题**:`hdc list targets` 输出 `[Empty]`
**应急**:
- 检查 USB 数据线(必须支持数据传输,不是仅充电)
- 检查 USB 调试是否打开
- 重启 hdc server:`hdc kill && hdc start`

### 问题 5:多设备冲突(连了多台鸿蒙)

**问题**:`hdc list targets` 输出多个设备
**应急**:
- 指定设备:`hdc -t 69F9K25C27023877 hilog`
- 拔掉其他鸿蒙设备

---

## 六、User 操作清单(连真机后,30 分钟)

- [ ] USB 连接 nova 15 Pro
- [ ] 打开 USB 调试
- [ ] `hdc list targets` → 看到序列号
- [ ] 跑 5 种 hilog 命令,各 5 分钟
- [ ] grep "com.zhishe.renovation.agent" → 找 V1.3 业务日志
- [ ] 截图 + 发 Mavis

---

## 七、Mavis 等 User 反馈

User 跑完 5 种 hilog 后:
- ✅ 有 V1.3 业务日志 → Mavis 抓 5 类问题日志,排查输出
- ❌ 5 种全无 V1.3 日志 → V1.3 装成功但启动失败,Mavis 排查签名 / 权限 / Intent

**Mavis 不在沙箱环境(没真机),只能等 User 真机测试反馈。**

---

**5 种 hilog 命令实测方案结束** — Mavis 2026-06-26 10:14

**Mavis 主动写本指南原因**:
- V1.3 装 nova 15 Pro 后,User 自己抓日志
- 5 种命令 + 5 大过滤方法
- 5 大已知问题提前预警
- 不让 User 在真机前手忙脚乱
