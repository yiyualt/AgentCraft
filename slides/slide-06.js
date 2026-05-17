// slide-06.js — Memory Trigger
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 6,
  title: '记忆触发器'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("Memory Trigger — 元认知监控器", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Left column: illustration card
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.3, w: 4.0, h: 3.8,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
    rectRadius: 0.15
  });

  // Card header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.3, w: 4.0, h: 0.06,
    fill: { color: theme.accent }
  });

  slide.addText("🎯 工作原理", {
    x: 0.7, y: 1.5, w: 3.6, h: 0.4,
    fontSize: 18, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  const triggerSteps = [
    { step: "①", text: "实时监控推理器的 Token 生成过程" },
    { step: "②", text: "在每个标点符号处计算\"调用概率\"" },
    { step: "③", text: "概率 > 阈值 → 触发记忆编织器" },
    { step: "④", text: "概率 ≤ 阈值 → 继续生成，不中断" }
  ];

  triggerSteps.forEach((item, i) => {
    const sy = 2.1 + i * 0.7;
    slide.addShape(pres.shapes.OVAL, {
      x: 0.8, y: sy, w: 0.35, h: 0.35,
      fill: { color: theme.accent }
    });
    slide.addText(item.step, {
      x: 0.8, y: sy, w: 0.35, h: 0.35,
      fontSize: 11, fontFace: "Arial",
      color: "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });
    slide.addText(item.text, {
      x: 1.3, y: sy, w: 3.0, h: 0.35,
      fontSize: 13, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "middle"
    });
  });

  // Right column: key points
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 4.8, y: 1.3, w: 4.7, h: 3.8,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
    rectRadius: 0.15
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 4.8, y: 1.3, w: 4.7, h: 0.06,
    fill: { color: theme.secondary }
  });

  slide.addText("⚡ 关键特性", {
    x: 5.0, y: 1.5, w: 4.3, h: 0.4,
    fontSize: 18, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  const features = [
    { title: "触发时机", desc: "仅在标点符号处（逗号、句号等语义边界），保证推理流畅性" },
    { title: "实现方式", desc: "轻量级 LoRA 适配器 + 强化学习训练（学会\"什么时候该回忆\"）" },
    { title: "设计巧思", desc: "不打断流畅推理，只在自然停顿处唤起记忆" },
    { title: "核心能力", desc: "元认知监控 — 实时感知推理状态并做出决策" }
  ];

  features.forEach((item, i) => {
    const sy = 2.1 + i * 0.75;
    slide.addText(item.title, {
      x: 5.1, y: sy, w: 4.2, h: 0.3,
      fontSize: 13, fontFace: "Microsoft YaHei",
      color: theme.accent, bold: true, align: "left", valign: "middle"
    });
    slide.addText(item.desc, {
      x: 5.1, y: sy + 0.3, w: 4.2, h: 0.35,
      fontSize: 11, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top"
    });
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("6", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: "Arial",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = { primary: "0a2463", secondary: "1e5fa3", accent: "3a86ff", light: "a8d5ff", bg: "e8f4ff" };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-06-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
