# zhishe-a2a ECS 主线归档(2026-07-08)

## 概要

`zhishe-a2a` 在 ECS 端的主线全部收口,公网业务零故障。

| 主线 | 实测结果 | 落盘时间 |
|------|----------|----------|
| 密钥对 `zhishe-ecs-2026-07-07` 创建 | `.pem` 1,704 B 已落 `~/.ssh/`,D 盘备份成功 | 2026-07-08 08:41 |
| 密钥对绑定 ECS 实例 | 控制台勾选 `i-2ze4ho11cy2zs6bgruki`,ECS 软重启 | 2026-07-08 10:29 |
| ECS 软件升级 | 50 包升级成功,内核 `19.5` → `19.6.a18`,reboot 1 次 | 2026-07-08 12:23 |
| SSH 密钥对登录验证 | `[root@...]#` 落定,`Last login ... from 112.41.88.140` | 2026-07-08 15:59 |
| 入方向规则收紧 | SSH 22 → `112.41.88.140/32`,RDP 3389 删除,ICMP 保留 | 2026-07-08 15:39 |
| 公网业务外部探测 | `/health`、`/v1/models`、`/.well-known/agent.json` 全 200,5 Skill 全暴露 | 2026-07-08 14:48 |

## 关键结论

1. **V1.4 V6.0 后端实际部署在 Windows 本机**,与 ECS 业务无关;ECS reboot 不影响公网。
2. 主机内 firewall-cmd/nftables/iptables 都未启用,SSH 22 由阿里云**安全组**统管。
3. ECS 公钥已纳入 `.ssh`,密码登录路径虽未明面关闭,但私钥已绑定 root,等阶段 6/7 后续处理。

## 后续动作

- 阶段 6:ECS 自动快照(策略绑定磁盘、按周一/三/五 03:00 触发)
- 阶段 4:子账号最小权限 + 主账号 AK 禁用
- ICP 备案号完整截图 + 公安联网备案 30 天内提交

## 公网快照锚点

- `GET https://tunnel.zhishe.top/health` → `{status:ok, service:zhishe-ai-renovation}`
- `GET https://tunnel.zhishe.top/v1/models` → `zhishe-a2a`
- `GET https://tunnel.zhishe.top/.well-known/agent.json` → V1.3.0, A2A 0.2.5

存档由 Mavis 写入,时间 `2026-07-08 16:04`。
