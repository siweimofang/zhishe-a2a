#!/bin/bash
# 知设 ECS 磁盘快照脚本(V3.0 第二桌面架构)
# 原文支撑:AI 寒武纪《云电脑改变了跑 Cursor 的方式》"就算真出了事,快照回滚,秒级恢复"
# 铁律 75 v2 第 7 项:默认私有
#
# 用法:
#   ./ecs_snapshot.sh daily    # 每日 03:00 自动跑(保留 7 天)
#   ./ecs_snapshot.sh weekly   # 每周日凌晨跑(保留 4 周)
#   ./ecs_snapshot.sh monthly  # 每月 1 号跑(保留 12 个月)
#   ./ecs_snapshot.sh pre-upgrade  # Skill 升级前手动跑

set -e

REGION="cn-shanghai"  # 华东 2 上海,与 DeepSeek API 同机房
INSTANCE_ID="i-2ze4ho11cy2zs6bgruki"  # 当前 ECS 实例
RETENTION_TYPE="${1:-daily}"  # 默认 daily

# === 颜色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# === 校验 aliyun CLI ===
if ! command -v aliyun > /dev/null 2>&1; then
    echo -e "${RED}❌ aliyun CLI 未安装,必先安装阿里云 CLI${NC}"
    echo "安装:https://help.aliyun.com/zh/ecs/getting-started/use-the-cli"
    exit 1
fi

# === 生成快照名称 ===
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
SNAPSHOT_NAME="zhishe-ecs-${RETENTION_TYPE}-${TIMESTAMP}"

# === 描述 ===
case "$RETENTION_TYPE" in
    daily)
        DESC="每日自动快照"
        TAG_KEY="Type"
        TAG_VALUE="DailySnapshot"
        ;;
    weekly)
        DESC="每周自动快照"
        TAG_KEY="Type"
        TAG_VALUE="WeeklySnapshot"
        ;;
    monthly)
        DESC="每月自动快照"
        TAG_KEY="Type"
        TAG_VALUE="MonthlySnapshot"
        ;;
    pre-upgrade)
        DESC="Skill 升级前快照(手动)"
        TAG_KEY="Type"
        TAG_VALUE="PreUpgradeSnapshot"
        ;;
    *)
        echo -e "${RED}❌ 无效 RETENTION_TYPE: $RETENTION_TYPE${NC}"
        echo "用法:$0 [daily|weekly|monthly|pre-upgrade]"
        exit 1
        ;;
esac

echo "=========================================="
echo "知设 ECS 磁盘快照"
echo "实例: $INSTANCE_ID"
echo "区域: $REGION"
echo "快照名: $SNAPSHOT_NAME"
echo "类型: $DESC"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# === 创建快照 ===
echo ""
echo "[1/3] 创建磁盘快照..."
SNAPSHOT_ID=$(aliyun ecs CreateSnapshot \
    --InstanceId "$INSTANCE_ID" \
    --Name "$SNAPSHOT_NAME" \
    --Description "$DESC" \
    --RegionId "$REGION" \
    --output json 2>&1 | python -c "import sys, json; print(json.load(sys.stdin)['SnapshotId'])")

if [ -z "$SNAPSHOT_ID" ]; then
    echo -e "${RED}❌ 快照创建失败${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 快照已创建: $SNAPSHOT_ID${NC}"

# === 打标签 ===
echo ""
echo "[2/3] 打标签..."
aliyun ecs TagResources \
    --ResourceId "["$SNAPSHOT_ID"]" \
    --Tag.1.Key "$TAG_KEY" \
    --Tag.1.Value "$TAG_VALUE" \
    --RegionId "$REGION" \
    --output json > /dev/null
echo -e "${GREEN}✅ 标签已打: $TAG_KEY=$TAG_VALUE${NC}"

# === 清理旧快照(按保留策略) ===
echo ""
echo "[3/3] 清理过期快照..."

case "$RETENTION_TYPE" in
    daily)
        KEEP_DAYS=7
        ;;
    weekly)
        KEEP_DAYS=28
        ;;
    monthly)
        KEEP_DAYS=365
        ;;
    pre-upgrade)
        KEEP_DAYS=30
        ;;
esac

CUTOFF_DATE=$(date -d "$KEEP_DAYS days ago" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -v -"$KEEP_DAYS"d '+%Y-%m-%dT%H:%M:%SZ')
echo "保留 $KEEP_DAYS 天(截止日期:$CUTOFF_DATE)"

# 列出本实例所有快照,过滤同类型且超过保留期的
SNAPSHOTS=$(aliyun ecs DescribeSnapshots \
    --InstanceId "$INSTANCE_ID" \
    --RegionId "$REGION" \
    --Status All \
    --output json 2>/dev/null | python -c "
import sys, json
from datetime import datetime
data = json.load(sys.stdin)
cutoff = datetime.strptime('$CUTOFF_DATE', '%Y-%m-%dT%H:%M:%SZ')
type_prefix = 'zhishe-ecs-$RETENTION_TYPE-'
for s in data.get('Snapshots', {}).get('Snapshot', []):
    name = s.get('Name', '')
    sid = s.get('SnapshotId', '')
    created = s.get('CreationTime', '')
    if name.startswith(type_prefix):
        try:
            ct = datetime.strptime(created, '%Y-%m-%dT%H:%M:%SZ')
            if ct < cutoff:
                print(sid + '|' + name)
        except ValueError:
            pass
")

DELETED=0
while IFS='|' read -r OLD_SNAPSHOT_ID OLD_NAME; do
    if [ -n "$OLD_SNAPSHOT_ID" ]; then
        echo "  删除过期快照: $OLD_NAME ($OLD_SNAPSHOT_ID)"
        aliyun ecs DeleteSnapshot \
            --SnapshotId "$OLD_SNAPSHOT_ID" \
            --RegionId "$REGION" \
            --output json > /dev/null 2>&1 || true
        DELETED=$((DELETED + 1))
    fi
done <<< "$SNAPSHOTS"

echo -e "${GREEN}✅ 清理完成:删除 $DELETED 个过期快照${NC}"

echo ""
echo "=========================================="
echo "快照操作完成"
echo "新快照: $SNAPSHOT_ID"
echo "保留策略: $RETENTION_TYPE = $KEEP_DAYS 天"
echo "=========================================="

# === 写日志 ===
LOG_DIR="$(dirname "$0")/../logs/snapshots"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/snapshot_$(date '+%Y%m').log"
echo "$(date '+%Y-%m-%d %H:%M:%S') | $RETENTION_TYPE | new=$SNAPSHOT_ID | deleted=$DELETED | retention=${KEEP_DAYS}d" >> "$LOG_FILE"

echo "日志: $LOG_FILE"