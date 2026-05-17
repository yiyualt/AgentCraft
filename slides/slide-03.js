// slide-03.js — Research Background: Two Paradigms Dilemma
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 3,
  title: '研究背景与动机'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("研究背景与动机", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  slide.addText("现有记忆系统两大范式的困境", {
    x: 0.5, y: 0.85, w: 9.0, h: 0.4,
    fontSize: 16, fontFace: "Microsoft YaHei",
    color: theme.secondary, align: "left"
  });

  // Left card — Parametric Memory
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.5, w: 4.2, h: 2.5,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
    rectRadius: 0.15
  });

  // Left card header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.5, w: 4.2, h: 0.55,
    fill: { color: theme.secondary }
  });
  slide.addText("参数化记忆（SFT / GRPO / DPO）", {
    x: 0.5, y: 1.5, w: 4.2, h: 0.55,
    fontSize: 14, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  slide.addText("✅ 优点：深度内化经验\n\n❌ 缺点：灾难性遗忘\n任务迁移时覆盖旧知识", {
    x: 0.7, y: 2.2, w: 3.8, h: 1.6,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.primary, align: "left", valign: "top",
    lineSpacingMultiple: 1.5
  });

  // Right card — Retrieval Memory
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.3, y: 1.5, w: 4.2, h: 2.5,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
    rectRadius: 0.15
  });

  // Right card header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 1.5, w: 4.2, h: 0.55,
    fill: { color: theme.accent }
  });
  slide.addText("检索式记忆（ExpeL / AWM / Mem0）", {
    x: 5.3, y: 1.5, w: 4.2, h: 0.55,
    fontSize: 14, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  slide.addText("✅ 优点：不修改参数，无遗忘\n\n❌ 缺点：记忆与推理分离\n检索→拼接，缺乏自然流畅性", {
    x: 5.5, y: 2.2, w: 3.8, h: 1.6,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.primary, align: "left", valign: "top",
    lineSpacingMultiple: 1.5
  });

  // Bottom conclusion box
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 4.3, w: 9.0, h: 0.8,
    fill: { color: theme.primary },
    rectRadius: 0.1
  });

  slide.addText("💡 人类大脑中，记忆与推理是交织进行的——边思考边唤起记忆\nMemGen 要让 AI Agent 也具备这种能力", {
    x: 0.7, y: 4.3, w: 8.6, h: 0.8,
    fontSize: 14, fontFace: "Microsoft YaHei",
    color: "FFFFFF", align: "center", valign: "middle",
    lineSpacingMultiple: 1.3
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("3", {
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
  pres.writeFile({ fileName: "slide-03-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
