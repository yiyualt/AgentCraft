// slide-08.js - Content: Memory & Tool Use
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 8,
  title: '记忆机制与工具使用'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("记忆机制与工具使用", {
    x: 0.5, y: 0.25, w: 9, h: 0.65,
    fontSize: 36, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left", margin: 0
  });

  // Two-column layout: left = Memory, right = Tool Use

  // === LEFT COLUMN: Memory ===
  // Section header
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.15, w: 4.2, h: 0.55,
    fill: { color: theme.primary },
    rectRadius: 0.06
  });
  slide.addText("记忆机制 (Memory)", {
    x: 0.5, y: 1.15, w: 4.2, h: 0.55,
    fontSize: 17, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  const memItems = [
    { label: "短期记忆", desc: "利用LLM上下文窗口存储\n当前任务的交互历史与中间结果" },
    { label: "长期记忆", desc: "基于向量数据库持久化存储\n关键信息，支持语义检索与召回" },
    { label: "工作记忆", desc: "结合RAG技术，动态检索与\n当前任务最相关的记忆片段" }
  ];

  memItems.forEach((item, i) => {
    const y = 1.95 + i * 1.1;

    // Icon circle
    slide.addShape(pres.shapes.OVAL, {
      x: 0.7, y: y + 0.1, w: 0.4, h: 0.4,
      fill: { color: theme.accent, transparency: 20 }
    });
    slide.addText(String(i + 1), {
      x: 0.7, y: y + 0.1, w: 0.4, h: 0.4,
      fontSize: 13, fontFace: "Georgia", color: theme.primary,
      bold: true, align: "center", valign: "middle"
    });

    // Label
    slide.addText(item.label, {
      x: 1.3, y: y - 0.05, w: 3.2, h: 0.35,
      fontSize: 15, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true,
      align: "left", valign: "middle", margin: 0
    });

    // Description
    slide.addText(item.desc, {
      x: 1.3, y: y + 0.3, w: 3.2, h: 0.7,
      fontSize: 11, fontFace: "Calibri",
      color: theme.secondary, bold: false,
      align: "left", valign: "top", margin: 0,
      lineSpacingMultiple: 1.3
    });
  });

  // === RIGHT COLUMN: Tool Use ===
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.2, y: 1.15, w: 4.3, h: 0.55,
    fill: { color: theme.secondary },
    rectRadius: 0.06
  });
  slide.addText("工具使用 (Tool Use)", {
    x: 5.2, y: 1.15, w: 4.3, h: 0.55,
    fontSize: 17, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  const toolItems = [
    { label: "API调用", desc: "通过函数调用接口与外部\n服务交互，获取实时数据" },
    { label: "代码执行", desc: "在沙箱环境中运行代码，\n完成计算、分析等复杂任务" },
    { label: "多模态交互", desc: "支持图像理解、文件处理，\n扩展智能体的感知与操作边界" }
  ];

  toolItems.forEach((item, i) => {
    const y = 1.95 + i * 1.1;

    slide.addShape(pres.shapes.OVAL, {
      x: 5.4, y: y + 0.1, w: 0.4, h: 0.4,
      fill: { color: theme.accent, transparency: 20 }
    });
    slide.addText(String(i + 1), {
      x: 5.4, y: y + 0.1, w: 0.4, h: 0.4,
      fontSize: 13, fontFace: "Georgia", color: theme.primary,
      bold: true, align: "center", valign: "middle"
    });

    slide.addText(item.label, {
      x: 6.0, y: y - 0.05, w: 3.3, h: 0.35,
      fontSize: 15, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true,
      align: "left", valign: "middle", margin: 0
    });

    slide.addText(item.desc, {
      x: 6.0, y: y + 0.3, w: 3.3, h: 0.7,
      fontSize: 11, fontFace: "Calibri",
      color: theme.secondary, bold: false,
      align: "left", valign: "top", margin: 0,
      lineSpacingMultiple: 1.3
    });
  });

  // Vertical divider between columns
  slide.addShape(pres.shapes.LINE, {
    x: 4.85, y: 1.4, w: 0, h: 3.8,
    line: { color: theme.light, width: 1.5 }
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("8", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: "Calibri",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = {
    primary: "03045e", secondary: "0077b6", accent: "00b4d8",
    light: "90e0ef", bg: "caf0f8"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-08-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
