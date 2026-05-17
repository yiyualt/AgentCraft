// slide-09.js — Experimental Results
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 9,
  title: '实验结果'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("实验结果（核心数据）", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Top row: 3 highlight cards
  const highlights = [
    { value: "13.44%", label: "超越 GRPO\n（参数化记忆）", color: theme.primary },
    { value: "38.22%", label: "超越 ExpeL/AWM\n（检索式记忆）", color: theme.accent },
    { value: "8", label: "基准全面超越\n（ALFWorld / TriviaQA / PopQA / KodCode / BigCodeBench / GPQA / GSM8K / MATH）", color: theme.secondary }
  ];

  const hw = 2.85;
  const hg = 0.25;
  const hsx = 0.45;

  highlights.forEach((h, i) => {
    const cx = hsx + i * (hw + hg);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.2, w: hw, h: 1.8,
      fill: { color: h.color },
      shadow: { type: "outer", blur: 6, offset: 2, color: "999999", opacity: 0.3 },
      rectRadius: 0.12
    });

    slide.addText(h.value, {
      x: cx, y: 1.3, w: hw, h: 0.8,
      fontSize: 32, fontFace: "Arial",
      color: "FFFFFF", bold: true, align: "center", valign: "middle"
    });

    slide.addText(h.label, {
      x: cx + 0.15, y: 2.15, w: hw - 0.3, h: 0.75,
      fontSize: 11, fontFace: "Microsoft YaHei",
      color: "FFFFFF", align: "center", valign: "top",
      lineSpacingMultiple: 1.3
    });
  });

  // Bottom row: 2 more findings
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.45, y: 3.3, w: 4.3, h: 1.5,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
    rectRadius: 0.12
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.45, y: 3.3, w: 4.3, h: 0.05,
    fill: { color: theme.accent }
  });

  slide.addText("🌐 跨域泛化能力", {
    x: 0.65, y: 3.45, w: 3.9, h: 0.35,
    fontSize: 14, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  slide.addText("仅在 KodCode 上训练 → MATH 任务从 36.6% 提升至 54.2%\n说明：MemGen 学会了\"如何调用记忆\"的通用能力", {
    x: 0.65, y: 3.85, w: 3.9, h: 0.8,
    fontSize: 12, fontFace: "Microsoft YaHei",
    color: theme.secondary, align: "left", valign: "top",
    lineSpacingMultiple: 1.4
  });

  // Second card
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.0, y: 3.3, w: 4.55, h: 1.5,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
    rectRadius: 0.12
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 3.3, w: 4.55, h: 0.05,
    fill: { color: theme.accent }
  });

  slide.addText("🛡️ 抗遗忘能力", {
    x: 5.2, y: 3.45, w: 4.15, h: 0.35,
    fontSize: 14, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  slide.addText("顺序训练多个任务后，MemGen 仍保持较高准确率\n而 ExpeL 和 SFT 出现明显遗忘\n→ 避免灾难性遗忘的关键优势", {
    x: 5.2, y: 3.85, w: 4.15, h: 0.8,
    fontSize: 12, fontFace: "Microsoft YaHei",
    color: theme.secondary, align: "left", valign: "top",
    lineSpacingMultiple: 1.4
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("9", {
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
  pres.writeFile({ fileName: "slide-09-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
