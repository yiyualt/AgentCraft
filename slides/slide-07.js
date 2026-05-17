// slide-07.js — Memory Weaver
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 7,
  title: '记忆编织器'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("Memory Weaver — 在潜在空间生成记忆", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Top row: 3 info cards
  const cardData = [
    { title: "📥 输入", text: "当前推理状态\n（推理器的隐藏层表示）" },
    { title: "📤 输出", text: "隐式记忆向量序列\n（Latent Memory Tokens）" },
    { title: "🎯 注入方式", text: "以隐藏状态注入\n无需转成自然语言" }
  ];

  const cw = 2.8;
  const cg = 0.3;
  const csx = 0.5;

  cardData.forEach((card, i) => {
    const cx = csx + i * (cw + cg);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.2, w: cw, h: 1.5,
      fill: { color: "FFFFFF" },
      shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
      rectRadius: 0.12
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: 1.2, w: cw, h: 0.05,
      fill: { color: theme.accent }
    });
    slide.addText(card.title, {
      x: cx + 0.15, y: 1.35, w: cw - 0.3, h: 0.35,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true, align: "left", valign: "middle"
    });
    slide.addText(card.text, {
      x: cx + 0.15, y: 1.75, w: cw - 0.3, h: 0.8,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top",
      lineSpacingMultiple: 1.3
    });
  });

  // Bottom section — comparison table
  slide.addText("隐式记忆 vs 显式记忆", {
    x: 0.5, y: 3.0, w: 9.0, h: 0.4,
    fontSize: 18, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Table header
  const tableRows = [
    [
      { text: "维度", options: { bold: true, color: "FFFFFF", fill: { color: theme.secondary }, fontSize: 12, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "隐式记忆 (MemGen)", options: { bold: true, color: "FFFFFF", fill: { color: theme.secondary }, fontSize: 12, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "显式记忆 (传统检索)", options: { bold: true, color: "FFFFFF", fill: { color: theme.secondary }, fontSize: 12, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } }
    ],
    [
      { text: "表示形式", options: { bold: true, color: theme.primary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "潜在空间向量（隐藏状态）", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "自然语言文本 (Chunk/Summary)", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } }
    ],
    [
      { text: "生成方式", options: { bold: true, color: theme.primary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "动态生成（每次可能不同）", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "从数据库检索（固定内容）", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } }
    ],
    [
      { text: "注入方式", options: { bold: true, color: theme.primary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "融入推理过程（无缝）", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } },
      { text: "拼接到上下文（拼接感）", options: { color: theme.secondary, fontSize: 11, fontFace: "Microsoft YaHei", align: "center", valign: "middle" } }
    ]
  ];

  slide.addTable(tableRows, {
    x: 0.5, y: 3.5, w: 9.0,
    colW: [1.5, 3.75, 3.75],
    rowH: [0.35, 0.35, 0.35, 0.35],
    border: { type: "solid", pt: 0.5, color: theme.light },
    autoPage: false
  });

  // Training note
  slide.addText("训练方式：SFT（监督微调）或 GRPO（强化学习）", {
    x: 0.5, y: 4.85, w: 5.0, h: 0.3,
    fontSize: 11, fontFace: "Microsoft YaHei",
    color: theme.accent, italic: true, align: "left"
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("7", {
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
  pres.writeFile({ fileName: "slide-07-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
