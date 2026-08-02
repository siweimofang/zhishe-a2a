# DevEco Studio GUI 编译操作指南(2026-06-28 17:23)

> 触发:Mavis 自动编译失败,需 User 打开 DevEco Studio GUI 操作
> 沙箱实证:3 个失职(Mavis 1 + User 2),已修 1 个,等 User 操作 SDK Manager
> 预计时长:10-15 分钟(SDK 下载 5-10 分钟 + 编译 5-10 分钟)

---

## 步骤 1:打开 DevEco Studio

**操作**:双击桌面 `DevEco Studio` 图标
**位置**(沙箱实证):`C:\Program Files\Huawei\DevEco Studio\deveco-studio.exe` 或类似入口
**等待**:5-10 秒启动

---

## 步骤 2:打开 SDK Manager

**操作路径**:
- 顶部菜单 **Tools**(中文:**工具**)
- 选择 **SDK Manager**(中文:**SDK 管理**)
- **等待**:5-10 秒加载

---

## 步骤 3:检查并修复 API 26 SDK

**操作路径**:
- 左侧标签选 **OpenHarmony SDK**(中文:**OpenHarmony SDK**)

### 3.1 找到 API Version 26

- 在列表里找 **"API Version 26.0.0(5.0.0(12))"** 或 **"API 26"**
- 或者类似名称:**OpenHarmony 5.0.0.23(API 12)** / **OpenHarmony 5.0.0.22(API 12)** 等

### 3.2 修复路径错误

**沙箱实证错误**(2026-06-28 17:23):
```
Component ArkTS:26.0.0.23 has been placed in the wrong place,
expect C:\Program Files\Huawei\DevEco Studio\sdk\26.0.0\ets,
actual C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\ets
```

**含义**:SDK 装在 `default\openharmony\`(旧路径),但 DevEco Studio 5.x 期望新路径 `26.0.0\`

**操作步骤**:
1. 找到 **"API Version 26"** 那一行
2. 右边显示 **"Installed at: C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony"** = 路径错
3. 点 **"Uninstall"** 卸载(等 30 秒 - 1 分钟)
4. 卸载完后重新点 **"Install"** 下载到正确路径(等 5-10 分钟)
5. 下载完后会显示 **"Installed at: C:\Program Files\Huawei\DevEco Studio\sdk\26.0.0"** = 成功

---

## 步骤 4:打开工程

**操作路径**:
- 顶部菜单 **File**(中文:**文件**)
- 选择 **Open**(中文:**打开**)
- 选目录:`D:\DevEcoProjects\zhishe_renovation_agent`
- 等 30 秒 - 1 分钟加载

---

## 步骤 5:Build HAP

**操作路径**:
- 顶部菜单 **Build**(中文:**构建**)
- 选择 **Build Hap(s)/APP(s)**(中文:**构建 Hap(s)/APP(s)**)
- 子菜单选 **Build Hap(s)**(中文:**构建 Hap(s)**)
- 等 5-10 分钟(首次编译慢)

### 成功标志

底部 Build 面板显示:
```
> Task :entry:default@BuildHap...
> Task :entry:default@SignHap...
BUILD SUCCESSFUL in 5m 23s
```

### 失败处理

如果显示 **BUILD FAILED**,看 Build 面板红色错误。常见错误:
1. SDK 路径仍错 → 回步骤 3 重装
2. compileSdkVersion 错误 → 已修(Mavis 改 `"26.0.0"` 字符串)
3. 模块未找到 → 检查 `entry/build-profile.json5`

**把错误日志截图或复制文字贴 Mavis,我帮你分析。**

---

## 步骤 6:找产物 HAP

**成功后路径**:
```
D:\DevEcoProjects\zhishe_renovation_agent\entry\build\default\outputs\default\entry-default-signed.hap
```

**说明**:这就是 V1.5 HAP 升级版的安装包。
- 包含 A + B + C 三阶段升级(单元测试 28 用例 + dark 主题 41 个元素 + AIUI 主动智能 5 page 升级)
- 字节数预期:~78 KB(Mavis 估算,实际看产物大小)
- 已含 AIOS 3 层架构总览 README + 10 文件 AIOS 层标注

---

## Mavis 已修的 1 个失职

`build-profile.json5` 的 `targetSdkVersion: 26` 改为 `"26.0.0"`(字符串格式,API 26+ 必填):

```json5
// 之前(Mavis 失职)
{
  "targetSdkVersion": 26,
  "compileSdkVersion": 26
}

// 现在(Mavis 修复)
{
  "targetSdkVersion": "26.0.0",
  "compileSdkVersion": "26.0.0"
}
```

---

## User 必干的 1 个 SDK Manager 操作

**SDK 26.0.0.23 必须重装到 `26.0.0\` 路径**(沙箱实证当前在 `default\openharmony\` 旧路径)
**5-10 分钟下载**
**0 成本(SDK 免费)**

---

## 后续(编译成功后)

1. **Mavis 自动跑 hilog 5 命令验证脚本准备**(`adb shell hilog -r 0x12345 ...` × 5)
2. **Mavis 写 V1.5 项目书 v4**(把 A + B + C 真实编译结果更新进去)
3. **Mavis 立跨项目铁律 88**:**任何"沙箱实证 API 适配"必真编译一次才算 100%**(Mavis 失职 105 立)
4. **User 装 HAP 到 nova 15 Pro 真机测试**(等 HarmonyOS 7 招募版推送 2026-06-30 前)

---

## 时间表(2026-06-28 17:24)

| 时间 | 动作 | 责任 |
|---|---|---|
| 17:24 | User 打开 DevEco Studio GUI | User |
| 17:25 | User 打开 SDK Manager | User |
| 17:30 | User 卸载 API 26 SDK + 重装到正确路径(5-10 分钟下载) | User |
| 17:40 | SDK 下载完成 | - |
| 17:41 | User 打开工程 + Build → Build Hap(s) | User |
| 17:50 | 编译完成(预计 5-10 分钟) | - |
| 17:51 | Mavis 写 V1.5 项目书 v4 + 立铁律 88 | Mavis |
| 17:55 | Mavis 准备 hilog 5 命令验证脚本 | Mavis |

---

**状态**:等 User 拍"我去做"
