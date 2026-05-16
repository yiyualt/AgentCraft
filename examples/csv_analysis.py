"""
CSV 数据分析工具
================
功能:
  1. 加载 CSV 文件并预览数据
  2. 基本统计信息（均值、中位数、标准差等）
  3. 缺失值检测
  4. 相关性热力图（数值列）
  5. 按类别分组统计
  6. 导出分析报告

用法:
  python csv_analysis.py <csv_file_path>
"""

import sys
import csv
import os
from collections import defaultdict
from typing import Any
import math
import json
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def read_csv(file_path: str) -> tuple[list[str], list[list[str]]]:
    """读取 CSV 文件，返回 (表头, 数据行)"""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV 文件为空")

    headers = rows[0]
    data = rows[1:]
    return headers, data


def try_parse_number(val: str) -> float | None:
    """尝试把字符串转成数字，失败返回 None"""
    val = val.strip()
    if val == "" or val == "-":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def is_numeric_column(values: list[str], threshold: float = 0.8) -> bool:
    """判断某列是否算数值列（可解析比例 >= threshold）"""
    if not values:
        return False
    parsed = sum(1 for v in values if try_parse_number(v) is not None)
    return parsed / len(values) >= threshold


# ═══════════════════════════════════════════════════════════════
# 统计分析
# ═══════════════════════════════════════════════════════════════

def basic_stats(values: list[float]) -> dict[str, float]:
    """数值列的基本统计量"""
    n = len(values)
    if n == 0:
        return {}

    mean_val = sum(values) / n
    sorted_vals = sorted(values)
    median_val = sorted_vals[n // 2] if n % 2 == 1 else (
        sorted_vals[n // 2 - 1] + sorted_vals[n // 2]
    ) / 2

    variance = sum((x - mean_val) ** 2 for x in values) / n
    std_val = math.sqrt(variance)

    return {
        "count": n,
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "std": round(std_val, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "range": round(max(values) - min(values), 4),
        "q25": round(sorted_vals[n // 4], 4),
        "q75": round(sorted_vals[3 * n // 4], 4),
    }


def missing_analysis(headers: list[str], data: list[list[str]]) -> list[dict[str, Any]]:
    """各列的缺失值分析"""
    total = len(data)
    result = []
    for col_idx, col_name in enumerate(headers):
        col_values = [row[col_idx] if col_idx < len(row) else "" for row in data]
        empty_count = sum(1 for v in col_values if v.strip() == "")
        empty_pct = round(empty_count / total * 100, 2)
        result.append({
            "column": col_name,
            "total": total,
            "missing": empty_count,
            "missing_pct": empty_pct,
            "filled": total - empty_count,
        })
    return result


def correlation_matrix(headers: list[str], data: list[list[str]],
                       numeric_cols: list[int]) -> list[list[float]]:
    """数值列之间的皮尔逊相关系数矩阵"""
    n = len(numeric_cols)
    if n < 2:
        return []

    # 提取数值矩阵
    matrix: list[list[float]] = []
    for row in data:
        vec: list[float] = []
        for ci in numeric_cols:
            val = try_parse_number(row[ci] if ci < len(row) else "")
            # 缺失值用该列均值填充（简化处理）
            vec.append(val if val is not None else 0.0)
        matrix.append(vec)

    # 计算均值
    means = []
    for j in range(n):
        col_vals = [matrix[i][j] for i in range(len(matrix))]
        means.append(sum(col_vals) / len(col_vals))

    # 计算相关系数
    corr = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                corr[i][j] = 1.0
                continue
            num = sum((matrix[k][i] - means[i]) * (matrix[k][j] - means[j])
                      for k in range(len(matrix)))
            den_i = math.sqrt(sum((matrix[k][i] - means[i]) ** 2
                                  for k in range(len(matrix))))
            den_j = math.sqrt(sum((matrix[k][j] - means[j]) ** 2
                                  for k in range(len(matrix))))
            den = den_i * den_j
            corr[i][j] = round(num / den, 4) if den != 0 else 0.0

    return corr


def group_stats(headers: list[str], data: list[list[str]],
                group_col: int, value_col: int) -> dict[str, dict[str, float]]:
    """按类别列分组，对数值列做统计"""
    groups: dict[str, list[float]] = defaultdict(list)
    for row in data:
        key = row[group_col] if group_col < len(row) else ""
        val = try_parse_number(row[value_col] if value_col < len(row) else "")
        if key and val is not None:
            groups[key].append(val)

    result = {}
    for key, vals in sorted(groups.items()):
        result[key] = basic_stats(vals)
    return result


# ═══════════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════════

def print_separator(char: str = "═", width: int = 70) -> None:
    print(char * width)


def print_header(title: str) -> None:
    print_separator()
    print(f"  {title}")
    print_separator()


def print_table(rows: list[list[Any]], headers: list[str]) -> None:
    """简易表格打印"""
    col_widths = [
        max(len(str(row[i])) if i < len(row) else 0
            for row in rows + [headers])
        for i in range(len(headers))
    ]
    # 限制最大宽度
    col_widths = [min(w, 30) for w in col_widths]

    def format_row(row: list[Any]) -> str:
        parts = []
        for i, h in enumerate(headers):
            val = str(row[i]) if i < len(row) else ""
            parts.append(val.ljust(col_widths[i]))
        return " | ".join(parts)

    print(format_row(headers))
    print("-+-".join("-" * w for w in col_widths))
    for row in rows:
        print(format_row(row))


def export_report(report: dict[str, Any], output_path: str) -> None:
    """导出分析报告为 JSON"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 报告已导出: {output_path}")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def analyze_csv(file_path: str) -> dict[str, Any]:
    """执行完整的 CSV 分析"""
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)

    # 1. 读取
    print_header(f"📂 加载文件: {file_path}")
    headers, data = read_csv(file_path)
    print(f"   列数: {len(headers)}")
    print(f"   行数: {len(data)} (不含表头)")
    print(f"   列名: {', '.join(headers)}")

    # 2. 预览
    print_header("👁️  数据预览 (前 5 行)")
    preview_rows = data[:5]
    print_table(preview_rows, headers)

    # 3. 数据类型推断
    print_header("🔍 列类型推断")
    numeric_indices: list[int] = []
    text_indices: list[int] = []
    for ci, col_name in enumerate(headers):
        col_values = [row[ci] if ci < len(row) else "" for row in data]
        if is_numeric_column(col_values):
            numeric_indices.append(ci)
            print(f"   ✅ {col_name:20s} → 数值型")
        else:
            text_indices.append(ci)
            print(f"   📝 {col_name:20s} → 文本型")

    # 4. 缺失值分析
    print_header("❓ 缺失值分析")
    missing = missing_analysis(headers, data)
    missing_rows = [
        [m["column"], m["total"], m["missing"], f"{m['missing_pct']}%"]
        for m in missing
    ]
    print_table(missing_rows, ["列名", "总数", "缺失数", "缺失率"])

    # 5. 数值列统计
    print_header("📊 数值列统计")
    report_stats = {}
    for ci in numeric_indices:
        col_values = [
            try_parse_number(row[ci] if ci < len(row) else "")
            for row in data
        ]
        vals = [v for v in col_values if v is not None]
        stats = basic_stats(vals)
        report_stats[headers[ci]] = stats

        print(f"\n  {headers[ci]}:")
        print(f"    数量: {stats['count']}  |  均值: {stats['mean']}")
        print(f"    中位数: {stats['median']}  |  标准差: {stats['std']}")
        print(f"    最小值: {stats['min']}  |  最大值: {stats['max']}")
        print(f"    四分位: Q1={stats['q25']}  Q3={stats['q75']}")

    # 6. 相关性分析
    if len(numeric_indices) >= 2:
        print_header("🔄 数值列相关性矩阵")
        corr = correlation_matrix(headers, data, numeric_indices)
        col_names = [headers[i] for i in numeric_indices]

        # 打印矩阵
        corr_display = [[""] + col_names]
        for i, name in enumerate(col_names):
            row_str = [name] + [str(corr[i][j]) for j in range(len(col_names))]
            corr_display.append(row_str)
        print_table(corr_display[1:], corr_display[0])

    # 7. 分组统计（如果有文本列和数值列）
    if text_indices and numeric_indices:
        print_header("📈 分组统计 (按文本列分组统计数值列)")
        # 用第一个文本列分组，第一个数值列统计
        gc = text_indices[0]
        vc = numeric_indices[0]
        print(f"   分组列: {headers[gc]}  →  统计列: {headers[vc]}")
        groups = group_stats(headers, data, gc, vc)
        group_rows = [
            [k, v["count"], v["mean"], v["median"], v["std"], v["min"], v["max"]]
            for k, v in groups.items()
        ]
        print_table(group_rows, ["分组", "数量", "均值", "中位数", "标准差", "最小值", "最大值"])

    # 8. 构建报告
    report = {
        "file": file_path,
        "columns": len(headers),
        "rows": len(data),
        "column_names": headers,
        "numeric_columns": [headers[i] for i in numeric_indices],
        "text_columns": [headers[i] for i in text_indices],
        "missing_analysis": missing,
        "statistics": report_stats,
        "analyzed_at": datetime.now().isoformat(),
    }

    return report


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python csv_analysis.py <csv_file_path>")
        print("示例: python csv_analysis.py data.csv")
        sys.exit(1)

    file_path = sys.argv[1]
    report = analyze_csv(file_path)

    # 导出报告
    output_dir = os.path.dirname(file_path) or "."
    report_path = os.path.join(
        output_dir,
        f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    export_report(report, report_path)

    print_separator("=")
    print(f"✅ 分析完成！")
    print_separator("=")


if __name__ == "__main__":
    main()
