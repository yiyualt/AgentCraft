"""
排序算法可视化
==============
功能:
  1. 冒泡排序 (Bubble Sort)
  2. 选择排序 (Selection Sort)
  3. 插入排序 (Insertion Sort)
  4. 快速排序 (Quick Sort)
  5. 归并排序 (Merge Sort)
  6. 终端彩色柱状图可视化每一步

用法:
  python sort_visualizer.py
"""

import time
import random
import os
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════════════
# 终端渲染
# ═══════════════════════════════════════════════════════════════

# ANSI 颜色
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

# 柱状图字符
BAR_CHARS = "█▇▆▅▄▃▂▁"


def clear_screen() -> None:
    """清屏"""
    os.system("clear" if os.name == "posix" else "cls")


def render_bars(arr: list[int],
                highlight: Optional[list[int]] = None,
                title: str = "") -> None:
    """
    在终端渲染柱状图。
    highlight: 需要高亮的下标列表（比如正在比较/交换的元素）
    """
    if highlight is None:
        highlight = []

    n = len(arr)
    if n == 0:
        return

    max_val = max(arr)
    min_val = min(arr)
    height = min(20, max_val - min_val + 1) if max_val > min_val else 1

    # 归一化到 [1, height]
    scaled = []
    for v in arr:
        if max_val == min_val:
            scaled.append(1)
        else:
            scaled.append(int((v - min_val) / (max_val - min_val) * (height - 1)) + 1)

    # 从顶往下画
    lines = []
    for h in range(height, 0, -1):
        line = ""
        for i in range(n):
            if scaled[i] >= h:
                color = RED if i in highlight else CYAN
                line += f"{color}██{RESET}"
            else:
                line += "  "
        lines.append(line)

    # 打印
    if title:
        print(f"\n{BOLD}{title}{RESET}\n")

    for line in lines:
        print(line)

    # 底部数值标签
    labels = " ".join(f"{v:2d}" for v in arr)
    print(f"  {labels}")
    print()


# ═══════════════════════════════════════════════════════════════
# 排序算法（带可视化回调）
# ═══════════════════════════════════════════════════════════════

SortCallback = Callable[[list[int], Optional[list[int]], str], None]


def bubble_sort(arr: list[int], callback: SortCallback) -> list[int]:
    """冒泡排序"""
    a = arr[:]
    n = len(a)
    callback(a, None, "🔄 冒泡排序 — 初始状态")

    for i in range(n):
        swapped = False
        for j in range(n - i - 1):
            callback(a, [j, j + 1], f"🔄 冒泡排序 — 第 {i+1} 轮, 比较 a[{j}] 和 a[{j+1}]")
            time.sleep(0.2)

            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                swapped = True
                callback(a, [j, j + 1], f"🔄 冒泡排序 — 交换 a[{j}] 和 a[{j+1}] ✅")
                time.sleep(0.3)

        if not swapped:
            callback(a, None, f"🔄 冒泡排序 — 第 {i+1} 轮 无交换, 提前结束 ✅")
            break

    callback(a, None, "✅ 冒泡排序 — 完成!")
    return a


def selection_sort(arr: list[int], callback: SortCallback) -> list[int]:
    """选择排序"""
    a = arr[:]
    n = len(a)
    callback(a, None, "📌 选择排序 — 初始状态")

    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            callback(a, [min_idx, j], f"📌 选择排序 — 第 {i+1} 轮, 比较 a[{min_idx}] 和 a[{j}]")
            time.sleep(0.2)

            if a[j] < a[min_idx]:
                min_idx = j

        if min_idx != i:
            a[i], a[min_idx] = a[min_idx], a[i]
            callback(a, [i, min_idx], f"📌 选择排序 — 交换 a[{i}] 和 a[{min_idx}] ✅")
            time.sleep(0.3)

    callback(a, None, "✅ 选择排序 — 完成!")
    return a


def insertion_sort(arr: list[int], callback: SortCallback) -> list[int]:
    """插入排序"""
    a = arr[:]
    n = len(a)
    callback(a, None, "🃏 插入排序 — 初始状态")

    for i in range(1, n):
        key = a[i]
        j = i - 1
        callback(a, [i], f"🃏 插入排序 — 第 {i} 步, 取 key = {key}")
        time.sleep(0.2)

        while j >= 0 and a[j] > key:
            a[j + 1] = a[j]
            callback(a, [j, j + 1], f"🃏 插入排序 — 右移 a[{j}] → a[{j+1}]")
            time.sleep(0.2)
            j -= 1

        a[j + 1] = key
        callback(a, [j + 1], f"🃏 插入排序 — 插入 {key} 到位置 {j+1}")
        time.sleep(0.3)

    callback(a, None, "✅ 插入排序 — 完成!")
    return a


def _quick_sort_rec(a: list[int], low: int, high: int,
                    callback: SortCallback) -> None:
    """快速排序递归"""
    if low < high:
        # 分区
        pivot = a[high]
        i = low - 1
        callback(a, [high], f"⚡ 快速排序 — 选择基准 pivot = {pivot} (下标 {high})")
        time.sleep(0.3)

        for j in range(low, high):
            callback(a, [j, high], f"⚡ 快速排序 — 比较 a[{j}]={a[j]} 和 pivot={pivot}")
            time.sleep(0.15)

            if a[j] < pivot:
                i += 1
                a[i], a[j] = a[j], a[i]
                if i != j:
                    callback(a, [i, j], f"⚡ 快速排序 — 交换 a[{i}] 和 a[{j}]")
                    time.sleep(0.2)

        a[i + 1], a[high] = a[high], a[i + 1]
        pi = i + 1
        callback(a, [pi], f"⚡ 快速排序 — pivot 归位, 分区点 = {pi}")
        time.sleep(0.3)

        _quick_sort_rec(a, low, pi - 1, callback)
        _quick_sort_rec(a, pi + 1, high, callback)


def quick_sort(arr: list[int], callback: SortCallback) -> list[int]:
    """快速排序"""
    a = arr[:]
    callback(a, None, "⚡ 快速排序 — 初始状态")
    _quick_sort_rec(a, 0, len(a) - 1, callback)
    callback(a, None, "✅ 快速排序 — 完成!")
    return a


def merge_sort(arr: list[int], callback: SortCallback) -> list[int]:
    """归并排序"""
    a = arr[:]
    callback(a, None, "🔀 归并排序 — 初始状态")

    # 非递归版本：自底向上
    n = len(a)
    width = 1
    while width < n:
        callback(a, None, f"🔀 归并排序 — 合并宽度 = {width}")
        time.sleep(0.3)

        for left in range(0, n, 2 * width):
            mid = min(left + width, n)
            right = min(left + 2 * width, n)

            # 合并 [left, mid) 和 [mid, right)
            left_part = a[left:mid]
            right_part = a[mid:right]
            i = j = 0
            k = left

            while i < len(left_part) and j < len(right_part):
                if left_part[i] <= right_part[j]:
                    a[k] = left_part[i]
                    i += 1
                else:
                    a[k] = right_part[j]
                    j += 1
                callback(a, [k], f"🔀 归并排序 — 填入 {a[k]}")
                time.sleep(0.1)
                k += 1

            while i < len(left_part):
                a[k] = left_part[i]
                callback(a, [k], f"🔀 归并排序 — 填入剩余 {a[k]}")
                time.sleep(0.1)
                i += 1
                k += 1

            while j < len(right_part):
                a[k] = right_part[j]
                callback(a, [k], f"🔀 归并排序 — 填入剩余 {a[k]}")
                time.sleep(0.1)
                j += 1
                k += 1

        width *= 2

    callback(a, None, "✅ 归并排序 — 完成!")
    return a


# ═══════════════════════════════════════════════════════════════
# 算法注册表
# ═══════════════════════════════════════════════════════════════

SORT_ALGORITHMS: dict[str, tuple[str, Callable]] = {
    "1": ("冒泡排序 (Bubble Sort)", bubble_sort),
    "2": ("选择排序 (Selection Sort)", selection_sort),
    "3": ("插入排序 (Insertion Sort)", insertion_sort),
    "4": ("快速排序 (Quick Sort)", quick_sort),
    "5": ("归并排序 (Merge Sort)", merge_sort),
}


def generate_data(size: int = 12, mode: str = "random") -> list[int]:
    """生成测试数据"""
    if mode == "random":
        return random.sample(range(1, size * 2 + 1), size)
    elif mode == "sorted":
        return list(range(1, size + 1))
    elif mode == "reversed":
        return list(range(size, 0, -1))
    elif mode == "few_unique":
        return [random.choice([3, 7, 15, 22, 30]) for _ in range(size)]
    else:
        return random.sample(range(1, size * 2 + 1), size)


# ═══════════════════════════════════════════════════════════════
# 主交互
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}       🎯 排序算法可视化 (终端版){RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}")
    print(f"\n  支持 5 种排序算法，实时柱状图展示每一步")
    print(f"  红色 = 正在操作的元素")
    print(f"  青色 = 已就绪的元素\n")

    # 数据规模
    try:
        size_input = input(f"  数据规模 (默认 10): ").strip()
        size = int(size_input) if size_input else 10
        size = max(4, min(30, size))
    except ValueError:
        size = 10

    # 数据模式
    print(f"\n  请选择数据模式:")
    print(f"    1. 随机 (random)")
    print(f"    2. 已排序 (sorted)")
    print(f"    3. 逆序 (reversed)")
    print(f"    4. 少量唯一值 (few_unique)")
    mode_choice = input(f"  请输入 (1-4, 默认 1): ").strip()
    mode_map = {"1": "random", "2": "sorted", "3": "reversed", "4": "few_unique"}
    mode = mode_map.get(mode_choice, "random")

    # 生成数据
    data = generate_data(size, mode)
    print(f"\n  📦 生成数据: {data}\n")

    # 选择算法
    print(f"  请选择排序算法:")
    for key, (name, _) in SORT_ALGORITHMS.items():
        print(f"    {key}. {name}")

    algo_choice = input(f"  请输入 (1-5, 默认 1): ").strip()
    if algo_choice not in SORT_ALGORITHMS:
        algo_choice = "1"

    algo_name, algo_func = SORT_ALGORITHMS[algo_choice]
    input(f"\n  🚀 按 Enter 开始 {algo_name}...")

    # 定义回调
    step_count = [0]

    def callback(arr: list[int], highlight: Optional[list[int]], title: str) -> None:
        clear_screen()
        step_count[0] += 1
        print(f"{BOLD}{'═' * 60}{RESET}")
        print(f"  步骤 {step_count[0]:3d}  |  {title}")
        print(f"{BOLD}{'═' * 60}{RESET}")
        render_bars(arr, highlight)

    # 执行排序
    start_time = time.time()
    result = algo_func(data, callback)
    elapsed = time.time() - start_time

    print(f"\n  ✅ 排序完成！")
    print(f"  原始: {data}")
    print(f"  结果: {result}")
    print(f"  正确: {'✅' if result == sorted(data) else '❌'}")
    print(f"  耗时: {elapsed:.2f} 秒")
    print(f"  步骤: {step_count[0]} 步\n")


if __name__ == "__main__":
    main()
