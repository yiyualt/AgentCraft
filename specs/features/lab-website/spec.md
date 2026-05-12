# Feature: Lab Website

## 背景

OfficeClaw 实验室需要一个展示科研成果、团队成员、研究方向的门户网站。这个网站由 Agent 辅助生成，验证 "Agent 构建 App" 的能力。

## 目标

- [x] 实验室首页（介绍、研究方向）
- [x] 团队成员页面
- [x] 科研成果/论文展示
- [x] 项目列表
- [x] 研究方向详情页
- [x] 研究交互流程展示
- [x] 响应式设计

## 页面结构

```
lab-website/
├── index.html           # 首页（实验室介绍）
├── team.html            # 团队成员
├── publications.html    # 科研成果/论文
├── projects.html        # 项目列表
├── research.html        # 研究方向总览
├── research-workflow.html    # 研究流程展示
├── research-interaction.html # 研究交互展示
├── source.html          # 资料来源/引用
├── script.js            # 通用脚本
└── styles.css           # 样式表
```

## 设计风格

- 学术风格，简洁专业
- 深色主题 + 科技感配色
- 响应式布局（移动端适配）
- 动态交互效果（过渡动画）

## 技术栈

- 纯 HTML/CSS/JS（无框架）
- CSS3 动画和 Flexbox/Grid 布局
- JavaScript 交互增强

## 内容模块

### 首页 (index.html)
- 实验室简介
- 核心研究方向卡片
- 最新成果轮播

### 研究方向 (research.html)
- AI4Science
- Agent Systems
- Human-AI Collaboration
- 智能办公

### 研究流程 (research-workflow.html)
- 可视化研究步骤流程图
- 交互式节点

### 研究交互 (research-interaction.html)
- 模拟 Agent 与研究者交互场景
- 动态对话展示

## 验证

```bash
# 本地预览
cd lab-website
python -m http.server 8080
# 打开 http://localhost:8080
```

## 后续扩展

- [ ] 多语言支持（英文/中文）
- [ ] 博客系统集成
- [ ] 搜索功能
- [ ] 后端数据管理