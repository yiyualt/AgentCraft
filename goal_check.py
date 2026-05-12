#!/usr/bin/env python3
"""每5秒检查一次时间，持续2分钟后退出"""

import time
import sys
import datetime

def main():
    duration = 120  # 2分钟
    interval = 5    # 5秒
    start_time = time.time()
    end_time = start_time + duration
    count = 0

    print("=" * 60)
    print("  🕐 每5秒检查时间，持续2分钟后退出")
    print(f"  开始时间: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"  预计结束: {datetime.datetime.fromtimestamp(end_time).strftime('%H:%M:%S')}")
    print(f"  预计检查次数: {duration // interval} 次")
    print("=" * 60)

    while True:
        now = time.time()
        if now >= end_time:
            break

        count += 1
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elapsed = int(now - start_time)
        remaining = int(end_time - now)

        print(f"  [{count:2d}] 当前时间: {current_time}  |  已过: {elapsed:3d}s  |  剩余: {remaining:3d}s")

        # 如果剩余时间不足一个间隔，则等待剩余时间
        sleep_time = min(interval, remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)

    print("=" * 60)
    print(f"  ✅ 完成！共检查了 {count} 次时间，2分钟已到。")
    print(f"  结束时间: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
