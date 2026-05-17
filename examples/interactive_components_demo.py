"""
交互组件使用示例 - Interactive Components Demo
================================================
展示 Canvas 系统中所有交互组件的使用方法。

组件类型 (7 种):
  1. option_list  - 选项列表（推荐，支持键盘导航 ↑↓ Enter Esc）
  2. button_group - 按钮组（多选按钮 + 确认）
  3. button       - 单按钮（确认/取消操作）
  4. form         - 表单（多字段输入）
  5. select       - 下拉选择框
  6. slider       - 数值滑块
  7. checkbox     - 布尔开关

架构:
  agent → canvas_interact() → CanvasManager → SSE Queue
                                                   ↓
  browser ← SSE Event ← CanvasChannel ← Queue.get()
                                                   ↓
  user clicks/form submit → POST /canvas/event/{session_id}
                              ↓
  agent receives "user_interaction" event in next turn

用法:
  python examples/interactive_components_demo.py
"""

import json
import logging
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 1. option_list - 选项列表（最推荐，最佳用户体验）
# ============================================================
# 适用场景: 让用户从多个选项中选择一个
# 前端体验: 键盘 ↑↓ 导航，Enter 确认，Esc 取消
# 前端渲染: 显示为可点击的列表项，带描述文字

def demo_option_list() -> dict[str, Any]:
    """创建一个选项列表交互组件。"""
    return {
        "component_type": "option_list",
        "config": {
            "options": [
                {
                    "value": "python",
                    "label": "Python 🐍",
                    "description": "通用编程语言，适合 AI/后端/自动化"
                },
                {
                    "value": "javascript",
                    "label": "JavaScript 💛",
                    "description": "前端必备，也可用于全栈开发"
                },
                {
                    "value": "go",
                    "label": "Go 🦍",
                    "description": "高性能后端语言，并发能力强"
                },
                {
                    "value": "rust",
                    "label": "Rust 🦀",
                    "description": "系统级语言，内存安全，性能极高"
                },
                {
                    "value": "typescript",
                    "label": "TypeScript 🔵",
                    "description": "JavaScript 的超集，类型安全"
                },
            ],
            "submit_label": "确认选择"  # 可选，默认 "确认"
        },
        "prompt": "请选择你想学习的编程语言: (使用 ↑↓ 键导航，Enter 确认)",
    }


# ============================================================
# 2. button_group - 按钮组（多选 + 确认）
# ============================================================
# 适用场景: 快速选择，不需要键盘导航
# 前端渲染: 水平排列的按钮，点击后高亮，点"确认"提交

def demo_button_group() -> dict[str, Any]:
    """创建一个按钮组交互组件。"""
    return {
        "component_type": "button_group",
        "config": {
            "options": [
                {"value": "daily", "label": "每日"},
                {"value": "weekly", "label": "每周"},
                {"value": "monthly", "label": "每月"},
                {"value": "custom", "label": "自定义"},
            ],
            "submit_label": "确定频率",
        },
        "prompt": "请选择报告生成频率:",
    }


# ============================================================
# 3. button - 单按钮（确认/取消）
# ============================================================
# 适用场景: 简单的 yes/no 确认，危险操作确认
# 样式: primary(默认), success(绿色), warning(黄色), danger(红色)

def demo_button() -> dict[str, Any]:
    """创建一个单按钮交互组件。"""
    return {
        "component_type": "button",
        "config": {
            "label": "是的，我确认删除",
            "style": "danger",  # primary | success | warning | danger
        },
        "prompt": "⚠️ 确定要删除这条记录吗？此操作不可恢复！",
    }


# ============================================================
# 4. form - 表单（多字段输入）
# ============================================================
# 适用场景: 需要用户输入文本、邮箱、密码等多字段信息
# 支持字段类型: text, email, password, number, textarea

def demo_form() -> dict[str, Any]:
    """创建一个表单交互组件。"""
    return {
        "component_type": "form",
        "config": {
            "fields": [
                {
                    "name": "name",
                    "type": "text",
                    "label": "姓名",
                    "placeholder": "请输入你的姓名",
                    "required": True,
                },
                {
                    "name": "email",
                    "type": "email",
                    "label": "邮箱",
                    "placeholder": "example@mail.com",
                    "required": True,
                },
                {
                    "name": "age",
                    "type": "number",
                    "label": "年龄",
                    "placeholder": "18-100",
                    "required": False,
                },
                {
                    "name": "bio",
                    "type": "textarea",
                    "label": "自我介绍",
                    "placeholder": "简单介绍一下自己...",
                    "required": False,
                },
            ]
        },
        "prompt": "请填写以下信息完成注册:",
    }


# ============================================================
# 5. select - 下拉选择框
# ============================================================
# 适用场景: 选项较多，需要节省界面空间
# 前端渲染: 浏览器原生 <select> 下拉框

def demo_select() -> dict[str, Any]:
    """创建一个下拉选择框交互组件。"""
    return {
        "component_type": "select",
        "config": {
            "options": [
                {"value": "beijing", "label": "北京"},
                {"value": "shanghai", "label": "上海"},
                {"value": "shenzhen", "label": "深圳"},
                {"value": "hangzhou", "label": "杭州"},
                {"value": "chengdu", "label": "成都"},
            ],
            "label": "选择城市",
        },
        "prompt": "请选择你的所在城市:",
    }


# ============================================================
# 6. slider - 数值滑块
# ============================================================
# 适用场景: 让用户选择连续范围的值（价格、数量、评分等）

def demo_slider() -> dict[str, Any]:
    """创建一个数值滑块交互组件。"""
    return {
        "component_type": "slider",
        "config": {
            "min": 0,
            "max": 100,
            "default": 50,
            "label": "进度",
        },
        "prompt": "请拖动滑块选择项目完成进度:",
    }


# ============================================================
# 7. checkbox - 布尔开关
# ============================================================
# 适用场景: 开/关设置，同意协议等

def demo_checkbox() -> dict[str, Any]:
    """创建一个布尔开关交互组件。"""
    return {
        "component_type": "checkbox",
        "config": {
            "label": "我同意服务条款和隐私政策",
            "checked": False,  # 默认状态
        },
        "prompt": "请确认以下条款:",
    }


# ============================================================
# 高级用法: 多步骤工作流
# ============================================================

def demo_multi_step_workflow() -> list[dict[str, Any]]:
    """
    演示多步骤交互流程。

    真实场景下，agent 会在收到上一步的用户选择后，
    再调用 canvas_interact 创建下一步的组件。
    这里展示完整的步骤定义。
    """
    steps = []

    # Step 1: 选择项目类型
    steps.append({
        "step": 1,
        "component": {
            "component_type": "option_list",
            "config": {
                "options": [
                    {"value": "web", "label": "Web 应用", "description": "基于浏览器的应用"},
                    {"value": "cli", "label": "命令行工具", "description": "终端/Shell 工具"},
                    {"value": "api", "label": "API 服务", "description": "RESTful/GraphQL API"},
                    {"value": "data", "label": "数据分析", "description": "数据处理/可视化"},
                ],
            },
            "prompt": "【第 1/3 步】请选择项目类型:",
        },
    })

    # Step 2: 选择技术栈（基于上一步的选择动态生成）
    steps.append({
        "step": 2,
        "component": {
            "component_type": "button_group",
            "config": {
                "options": [
                    {"value": "fastapi", "label": "FastAPI"},
                    {"value": "flask", "label": "Flask"},
                    {"value": "django", "label": "Django"},
                ],
                "submit_label": "确定框架",
            },
            "prompt": "【第 2/3 步】请选择 Python Web 框架:",
        },
    })

    # Step 3: 填写额外配置
    steps.append({
        "step": 3,
        "component": {
            "component_type": "form",
            "config": {
                "fields": [
                    {
                        "name": "project_name",
                        "type": "text",
                        "label": "项目名称",
                        "placeholder": "my-awesome-project",
                        "required": True,
                    },
                    {
                        "name": "description",
                        "type": "textarea",
                        "label": "项目描述",
                        "placeholder": "简单描述项目功能...",
                        "required": False,
                    },
                ],
            },
            "prompt": "【第 3/3 步】最后，请填写项目信息:",
        },
    })

    return steps


# ============================================================
# 如何在项目中使用 canvas_interact
# ============================================================

# 在你的 agent/tool 代码中调用方式如下:
#
#   from tools.builtin.canvas_tools import canvas_interact
#
#   # 创建交互组件
#   result = canvas_interact(
#       component_type="option_list",
#       config={
#           "options": [
#               {"value": "opt1", "label": "选项 1", "description": "描述文字"},
#               {"value": "opt2", "label": "选项 2"},
#           ],
#           "submit_label": "确认",
#       },
#       prompt="请选择一个选项:",
#   )
#
#   # result: "[Canvas] Interactive component created: id=comp_a1b2c3d4, type=option_list. ..."
#
#   用户选择后，下一轮对话会收到事件:
#   {
#       "type": "user_interaction",
#       "id": "comp_a1b2c3d4",
#       "event_type": "selection",
#       "data": {
#           "selected_value": "opt1",
#           "selected_label": "选项 1",
#           "selected_index": 0
#       }
#   }


# ============================================================
# 主函数 - 打印所有组件示例
# ============================================================

def main():
    """打印所有交互组件示例的定义。"""
    demos = [
        ("option_list - 选项列表（推荐）", demo_option_list()),
        ("button_group - 按钮组", demo_button_group()),
        ("button - 单按钮", demo_button()),
        ("form - 表单", demo_form()),
        ("select - 下拉选择框", demo_select()),
        ("slider - 数值滑块", demo_slider()),
        ("checkbox - 布尔开关", demo_checkbox()),
    ]

    print("=" * 70)
    print("   Canvas 交互组件使用示例")
    print("=" * 70)

    for i, (title, demo) in enumerate(demos, 1):
        print(f"\n{i}. {title}")
        print("-" * 70)
        print(f"   component_type: {demo['component_type']}")
        print(f"   config: {json.dumps(demo['config'], ensure_ascii=False, indent=4)}")
        print(f"   prompt: {demo['prompt']}")

    # 多步骤工作流
    print(f"\n\n{'=' * 70}")
    print("   高级用法: 多步骤工作流")
    print("=" * 70)

    steps = demo_multi_step_workflow()
    for step in steps:
        comp = step["component"]
        print(f"\n   Step {step['step']}: {comp['prompt']}")
        print(f"   component_type: {comp['component_type']}")
        print(f"   config options count: {len(comp['config'].get('options', comp['config'].get('fields', [])))}")

    print(f"\n\n{'=' * 70}")
    print("   组件类型 vs 适用场景速查表")
    print("=" * 70)
    print(f"   {'组件':<18} {'适用场景':<36} {'用户体验':<16}")
    print(f"   {'-'*18} {'-'*36} {'-'*16}")
    print(f"   {'option_list':<18} {'多选一，带描述':<36} {'⭐⭐⭐⭐⭐':<16}")
    print(f"   {'button_group':<18} {'快速多选确认':<36} {'⭐⭐⭐⭐':<16}")
    print(f"   {'button':<18} {'简单 yes/no 确认':<36} {'⭐⭐⭐':<16}")
    print(f"   {'form':<18} {'多字段文本输入':<36} {'⭐⭐⭐':<16}")
    print(f"   {'select':<18} {'选项多，省空间':<36} {'⭐⭐⭐':<16}")
    print(f"   {'slider':<18} {'连续数值选择':<36} {'⭐⭐⭐':<16}")
    print(f"   {'checkbox':<18} {'开/关，接受条款':<36} {'⭐⭐⭐':<16}")
    print()


if __name__ == "__main__":
    main()
