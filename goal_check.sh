#!/bin/bash

echo "=== 开始每5秒检查时间，持续2分钟（共24次检查）==="
echo ""

START_TIME=$(date +%s)
END_TIME=$((START_TIME + 120))
COUNT=0

while [ $(date +%s) -lt $END_TIME ]; do
    COUNT=$((COUNT + 1))
    NOW=$(date '+%Y-%m-%d %H:%M:%S')
    ELAPSED=$(( $(date +%s) - START_TIME ))
    REMAINING=$((120 - ELAPSED))
    echo "[$COUNT] 当前时间: $NOW | 已过: ${ELAPSED}秒 | 剩余: ${REMAINING}秒"
    sleep 5
done

echo ""
echo "✅ 完成！2分钟已到，共检查了 $COUNT 次时间。"
