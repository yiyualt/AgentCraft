"""
密码生成器
=========
功能:
  1. 生成随机密码（可自定义长度、字符集）
  2. 生成可读密码（类似 Bitwarden/Diceware 风格）
  3. 密码强度评估
  4. 批量生成
  5. 复制到剪贴板

用法:
  python password_generator.py          # 交互式
  python password_generator.py --cli     # 命令行模式
"""

import argparse
import random
import string
import math
import sys
import os
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# 字符集常量
# ═══════════════════════════════════════════════════════════════

LOWERCASE = string.ascii_lowercase        # a-z
UPPERCASE = string.ascii_uppercase        # A-Z
DIGITS = string.digits                    # 0-9
SYMBOLS = "!@#$%^&*()_+-=[]{}|;:,.<>?/~"

# 易混淆字符（生成可读密码时排除）
AMBIGUOUS = "0O1lI5S2Z8B"

# Diceware 词表（常用英文单词，用于生成可读密码）
DICEWARE_WORDS = [
    "apple", "baker", "crane", "dance", "eagle", "flame", "grape",
    "house", "image", "joker", "knife", "lemon", "mango", "noble",
    "ocean", "piano", "queen", "river", "snake", "tiger", "uncle",
    "voice", "whale", "xenon", "yacht", "zebra",
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
    "hotel", "india", "juliett", "kilo", "lima", "mike", "november",
    "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
    "victor", "whiskey", "xray", "yankee", "zulu",
    "brook", "cloud", "dream", "earth", "frost", "green", "heart",
    "iron", "jewel", "kraft", "light", "march", "night", "oasis",
    "peace", "quest", "ratio", "sugar", "trust", "ultra", "vivid",
    "winter", "xerox", "yield", "zones",
]


# ═══════════════════════════════════════════════════════════════
# 密码生成
# ═══════════════════════════════════════════════════════════════

def generate_random_password(
    length: int = 16,
    use_lower: bool = True,
    use_upper: bool = True,
    use_digits: bool = True,
    use_symbols: bool = False,
    exclude_ambiguous: bool = False,
) -> str:
    """
    生成随机密码。

    参数:
        length: 密码长度
        use_lower: 是否包含小写字母
        use_upper: 是否包含大写字母
        use_digits: 是否包含数字
        use_symbols: 是否包含符号
        exclude_ambiguous: 是否排除易混淆字符

    返回:
        生成的密码字符串
    """
    charset = ""
    if use_lower:
        charset += LOWERCASE
    if use_upper:
        charset += UPPERCASE
    if use_digits:
        charset += DIGITS
    if use_symbols:
        charset += SYMBOLS

    if not charset:
        charset = LOWERCASE + UPPERCASE + DIGITS

    if exclude_ambiguous:
        charset = "".join(c for c in charset if c not in AMBIGUOUS)

    if length < 1:
        length = 1

    # 确保每种选中的字符集至少出现一次
    password_parts = []
    remaining_length = length

    if use_lower and remaining_length > 0:
        password_parts.append(random.choice([c for c in LOWERCASE
                                             if c in charset]))
        remaining_length -= 1
    if use_upper and remaining_length > 0:
        password_parts.append(random.choice([c for c in UPPERCASE
                                             if c in charset]))
        remaining_length -= 1
    if use_digits and remaining_length > 0:
        password_parts.append(random.choice([c for c in DIGITS
                                             if c in charset]))
        remaining_length -= 1
    if use_symbols and remaining_length > 0:
        password_parts.append(random.choice([c for c in SYMBOLS
                                             if c in charset]))
        remaining_length -= 1

    # 填充剩余长度
    password_parts.extend(random.choices(charset, k=remaining_length))

    # 打乱顺序
    random.shuffle(password_parts)
    return "".join(password_parts)


def generate_readable_password(
    num_words: int = 4,
    separator: str = "-",
    capitalize: bool = False,
    add_digit: bool = True,
    add_symbol: bool = False,
) -> str:
    """
    生成可读密码（Diceware 风格）。

    参数:
        num_words: 单词数量
        separator: 分隔符
        capitalize: 是否首字母大写
        add_digit: 是否末尾追加数字
        add_symbol: 是否末尾追加符号

    返回:
        可读密码字符串
    """
    words = random.choices(DICEWARE_WORDS, k=num_words)

    if capitalize:
        words = [w.capitalize() for w in words]

    password = separator.join(words)

    suffix = ""
    if add_digit:
        suffix += str(random.randint(0, 99))
    if add_symbol:
        suffix += random.choice("!@#$%^&*")

    if suffix:
        password += separator + suffix

    return password


def generate_pin(length: int = 6) -> str:
    """生成纯数字 PIN 码"""
    if length < 1:
        length = 1
    return "".join(random.choices(DIGITS, k=length))


def generate_api_key(prefix: str = "sk-", byte_length: int = 32) -> str:
    """
    生成 API Key (类似 OpenAI 格式)。

    参数:
        prefix: 前缀
        byte_length: 随机字节长度

    返回:
        API Key 字符串
    """
    import secrets
    random_bytes = secrets.token_hex(byte_length)
    return f"{prefix}{random_bytes}"


# ═══════════════════════════════════════════════════════════════
# 密码强度评估
# ═══════════════════════════════════════════════════════════════

def estimate_entropy(password: str) -> float:
    """
    估算密码熵值（单位：比特）。
    熵越高 → 越难被暴力破解。
    """
    pool_size = 0

    if any(c in LOWERCASE for c in password):
        pool_size += 26
    if any(c in UPPERCASE for c in password):
        pool_size += 26
    if any(c in DIGITS for c in password):
        pool_size += 10
    if any(c in SYMBOLS for c in password):
        pool_size += len(SYMBOLS)

    if pool_size == 0:
        return 0.0

    return len(password) * math.log2(pool_size)


def strength_label(entropy: float) -> tuple[str, str, int]:
    """
    根据熵值返回强度标签、颜色代码和建议最小长度。

    返回: (标签, 颜色ANSI码, 建议最小长度)
    """
    if entropy < 30:
        return ("非常弱", "\033[91m", 8)
    elif entropy < 50:
        return ("弱", "\033[93m", 12)
    elif entropy < 70:
        return ("中等", "\033[94m", 16)
    elif entropy < 100:
        return ("强", "\033[92m", 20)
    else:
        return ("非常强", "\033[92m\033[1m", 24)


def evaluate_password(password: str) -> dict:
    """
    全面评估密码强度。

    返回包含各项指标的字典。
    """
    length = len(password)
    entropy = estimate_entropy(password)
    label, color, _ = strength_label(entropy)

    # 常见弱点检测
    warnings = []

    if length < 8:
        warnings.append("密码长度不足 8 位，极不安全")
    if password.isdigit():
        warnings.append("纯数字密码容易被暴力破解")
    if password.isalpha():
        warnings.append("纯字母密码强度不足")
    if password.islower():
        warnings.append("建议混合大小写字母")
    if password.isupper():
        warnings.append("建议混合大小写字母")
    if not any(c in DIGITS for c in password):
        warnings.append("建议包含数字")
    if not any(c in SYMBOLS for c in password):
        warnings.append("建议包含特殊符号")

    # 重复模式检测
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:
            warnings.append(f"存在重复字符 '{password[i]}' 连续出现")
            break

    # 常见密码检测
    common_passwords = {
        "password", "123456", "12345678", "qwerty", "abc123",
        "password123", "admin", "letmein", "welcome", "monkey",
        "dragon", "master", "111111", "123123", "iloveyou",
    }
    if password.lower() in common_passwords:
        warnings.append("这是常见密码，极易被破解")

    return {
        "password": password,
        "length": length,
        "entropy": round(entropy, 2),
        "strength": label,
        "has_lower": any(c in LOWERCASE for c in password),
        "has_upper": any(c in UPPERCASE for c in password),
        "has_digit": any(c in DIGITS for c in password),
        "has_symbol": any(c in SYMBOLS for c in password),
        "warnings": warnings,
    }


def print_evaluation(result: dict) -> None:
    """打印密码评估结果"""
    RESET = "\033[0m"
    label = result["strength"]
    color = strength_label(result["entropy"])[1]

    print(f"\n{'─' * 50}")
    print(f"  📋 密码评估报告")
    print(f"{'─' * 50}")
    print(f"  密码:   {result['password']}")
    print(f"  长度:   {result['length']} 位")
    print(f"  熵值:   {result['entropy']} 比特")
    print(f"  强度:   {color}{label}{RESET}")
    print(f"  组成:")
    print(f"    {'✅' if result['has_lower'] else '❌'} 小写字母")
    print(f"    {'✅' if result['has_upper'] else '❌'} 大写字母")
    print(f"    {'✅' if result['has_digit'] else '❌'} 数字")
    print(f"    {'✅' if result['has_symbol'] else '❌'} 符号")

    if result["warnings"]:
        print(f"\n  ⚠️  警告:")
        for w in result["warnings"]:
            print(f"    - {w}")
    else:
        print(f"\n  ✅ 未发现明显弱点")
    print(f"{'─' * 50}\n")


# ═══════════════════════════════════════════════════════════════
# 剪贴板支持（macOS pbcopy）
# ═══════════════════════════════════════════════════════════════

def copy_to_clipboard(text: str) -> bool:
    """复制文本到系统剪贴板（仅 macOS）"""
    try:
        import subprocess
        process = subprocess.Popen(
            "pbcopy", env={"LANG": "en_US.UTF-8"}, stdin=subprocess.PIPE
        )
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 交互式界面
# ═══════════════════════════════════════════════════════════════

def interactive_mode() -> None:
    """交互式菜单"""
    print(f"\n{'═' * 50}")
    print(f"     🔑 密码生成器 — 交互模式")
    print(f"{'═' * 50}")

    while True:
        print(f"\n  请选择密码类型:")
        print(f"    1. 随机密码 (可自定义)")
        print(f"    2. 可读密码 (单词组合)")
        print(f"    3. PIN 码 (纯数字)")
        print(f"    4. API Key")
        print(f"    5. 评估已有密码")
        print(f"    0. 退出")

        choice = input(f"\n  请输入 (0-5): ").strip()

        if choice == "0":
            print(f"\n  👋 再见!\n")
            break

        elif choice == "1":
            # 随机密码
            try:
                length = int(input(f"  长度 (默认 16): ").strip() or "16")
            except ValueError:
                length = 16

            use_symbols = input(f"  包含特殊符号? (y/n, 默认 n): ").strip().lower() == "y"
            exclude_amb = input(f"  排除易混淆字符? (y/n, 默认 y): ").strip().lower() != "n"
            count = input(f"  生成数量 (默认 5): ").strip()
            count = int(count) if count.isdigit() else 5

            print(f"\n  📝 生成的密码:")
            print(f"{'─' * 50}")
            passwords = []
            for _ in range(count):
                pwd = generate_random_password(
                    length=length, use_symbols=use_symbols,
                    exclude_ambiguous=exclude_amb,
                )
                passwords.append(pwd)
                eval_result = evaluate_password(pwd)
                color = strength_label(eval_result["entropy"])[1]
                print(f"    {color}{pwd}\033[0m  ({eval_result['entropy']} bits)")

            # 复制第一个到剪贴板
            if passwords and copy_to_clipboard(passwords[0]):
                print(f"\n  📋 已复制第一个密码到剪贴板!")

        elif choice == "2":
            # 可读密码
            try:
                words = int(input(f"  单词数量 (默认 4): ").strip() or "4")
            except ValueError:
                words = 4
            sep = input(f"  分隔符 (默认 '-'): ").strip() or "-"
            cap = input(f"  首字母大写? (y/n, 默认 n): ").strip().lower() == "y"
            digit = input(f"  追加数字? (y/n, 默认 y): ").strip().lower() != "n"

            count = input(f"  生成数量 (默认 5): ").strip()
            count = int(count) if count.isdigit() else 5

            print(f"\n  📝 可读密码:")
            print(f"{'─' * 50}")
            passwords = []
            for _ in range(count):
                pwd = generate_readable_password(
                    num_words=words, separator=sep,
                    capitalize=cap, add_digit=digit,
                )
                passwords.append(pwd)
                eval_result = evaluate_password(pwd)
                color = strength_label(eval_result["entropy"])[1]
                print(f"    {color}{pwd}\033[0m  ({eval_result['entropy']} bits)")

            if passwords and copy_to_clipboard(passwords[0]):
                print(f"\n  📋 已复制第一个密码到剪贴板!")

        elif choice == "3":
            try:
                length = int(input(f"  PIN 码位数 (默认 6): ").strip() or "6")
            except ValueError:
                length = 6
            count = int(input(f"  生成数量 (默认 5): ").strip() or "5")
            print(f"\n  📝 PIN 码:")
            for _ in range(count):
                print(f"    {generate_pin(length)}")

        elif choice == "4":
            prefix = input(f"  前缀 (默认 'sk-'): ").strip() or "sk-"
            print(f"\n  📝 API Key:")
            print(f"    {generate_api_key(prefix)}")

        elif choice == "5":
            pwd = input(f"  请输入要评估的密码: ").strip()
            if pwd:
                print_evaluation(evaluate_password(pwd))

        else:
            print(f"\n  ❌ 无效选择，请重试")


# ═══════════════════════════════════════════════════════════════
# 命令行模式
# ═══════════════════════════════════════════════════════════════

def cli_mode(args: argparse.Namespace) -> None:
    """命令行模式"""
    if args.evaluate:
        pwd = args.evaluate
        print_evaluation(evaluate_password(pwd))
        return

    if args.type == "random":
        pwd = generate_random_password(
            length=args.length,
            use_symbols=args.symbols,
            exclude_ambiguous=not args.ambiguous,
        )
    elif args.type == "readable":
        pwd = generate_readable_password(
            num_words=args.words,
            separator=args.separator,
            capitalize=args.capitalize,
            add_digit=args.digit,
        )
    elif args.type == "pin":
        pwd = generate_pin(length=args.length)
    elif args.type == "apikey":
        pwd = generate_api_key(prefix=args.prefix)
    else:
        pwd = generate_random_password(length=args.length)

    print(pwd, end="")

    if args.copy:
        if copy_to_clipboard(pwd):
            print(f"  (已复制到剪贴板)")
        else:
            print(f"  (复制失败，请手动复制)")


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="🔑 密码生成器 — 生成安全的随机密码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python password_generator.py                              # 交互模式
  python password_generator.py --cli                        # 默认随机 16 位
  python password_generator.py --cli -t random -l 20 -s     # 20位 + 符号
  python password_generator.py --cli -t readable -w 5       # 5单词可读密码
  python password_generator.py --cli -t pin -l 8            # 8位PIN码
  python password_generator.py --cli -t apikey              # API Key
  python password_generator.py --cli -e "MyP@ss123"         # 评估密码
  python password_generator.py --cli --copy                 # 复制到剪贴板
        """,
    )

    parser.add_argument("--cli", action="store_true", help="命令行模式（非交互）")

    # 类型
    parser.add_argument("-t", "--type",
                        choices=["random", "readable", "pin", "apikey"],
                        default="random", help="密码类型 (默认 random)")

    # 通用
    parser.add_argument("-l", "--length", type=int, default=16,
                        help="密码长度 (默认 16)")
    parser.add_argument("--copy", action="store_true",
                        help="复制到剪贴板")

    # 随机密码选项
    parser.add_argument("-s", "--symbols", action="store_true",
                        help="包含特殊符号")
    parser.add_argument("--ambiguous", action="store_true",
                        help="保留易混淆字符 (默认排除)")

    # 可读密码选项
    parser.add_argument("-w", "--words", type=int, default=4,
                        help="单词数量 (默认 4)")
    parser.add_argument("--separator", type=str, default="-",
                        help="分隔符 (默认 '-')")
    parser.add_argument("--capitalize", action="store_true",
                        help="单词首字母大写")
    parser.add_argument("--digit", action="store_true",
                        help="追加数字")

    # API Key
    parser.add_argument("--prefix", type=str, default="sk-",
                        help="API Key 前缀 (默认 'sk-')")

    # 评估
    parser.add_argument("-e", "--evaluate", type=str, metavar="PASSWORD",
                        help="评估已有密码强度")

    args = parser.parse_args()

    if not args.cli and not args.evaluate:
        interactive_mode()
    else:
        cli_mode(args)


if __name__ == "__main__":
    main()
