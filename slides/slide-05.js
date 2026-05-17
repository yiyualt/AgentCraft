// slide-05.js — Architecture Overview
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 5,
  title: '架构总览'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("MemGen 架构 — 双引擎系统", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Flow diagram using boxes and arrows

  // Step 1: 推理器生成Token
  const boxY = 1.3;
  const boxH = 0.6;
  const arrowH = 0.35;

  const addProcessBox = (label, x, w, color, textColor) => {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: boxY, w: w, h: boxH,
      fill: { color: color },
      rectRadius: 0.08
    });
    slide.addText(label, {
      x: x, y: boxY, w: w, h: boxH,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: textColor || "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });
  };

  const addArrow = (x, fromY, toY, color) => {
    const midY = (fromY + toY) / 2;
    slide.addShape(pres.shapes.LINE, {
      x: x, y: fromY, w: 0, h: toY - fromY,
      line: { color: color || theme.secondary, width: 2 },
      lineEnd: "triangle"
    });
  };

  const addHorizArrow = (fromX, toX, y, color) => {
    slide.addShape(pres.shapes.LINE, {
      x: fromX, y: y, w: toX - fromX, h: 0,
      line: { color: color || theme.secondary, width: 2 },
      lineEnd: "triangle"
    });
  };

  // Row 1: 推理器生成Token → (标点检测)
  addProcessBox("推理器生成 Token", 0.5, 2.5, theme.secondary);
  addProcessBox("检测到标点符号", 3.3, 2.0, theme.light, theme.primary);
  addHorizArrow(3.0, 3.3, boxY + boxH/2, theme.secondary);

  // Down arrow to trigger decision
  slide.addShape(pres.shapes.LINE, {
    x: 4.3, y: boxY + boxH, w: 0, h: 0.3,
    line: { color: theme.secondary, width: 2 },
    lineEnd: "triangle"
  });

  // Decision diamond: 概率 > 阈值?
  const decY = boxY + boxH + 0.3;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 3.5, y: decY, w: 1.6, h: 0.55,
    fill: { color: theme.accent },
    rectRadius: 0.08
  });
  slide.addText("概率 > 阈值?", {
    x: 3.5, y: decY, w: 1.6, h: 0.55,
    fontSize: 11, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  // Yes arrow going right
  slide.addShape(pres.shapes.LINE, {
    x: 5.1, y: decY + 0.275, w: 0.8, h: 0,
    line: { color: theme.accent, width: 2 },
    lineEnd: "triangle"
  });
  slide.addText("是", {
    x: 5.25, y: decY + 0.2, w: 0.5, h: 0.3,
    fontSize: 10, fontFace: "Arial",
    color: theme.accent, bold: true, align: "center"
  });

  // Step 2: Memory Weaver
  const weaverY = decY + 0.8;
  addProcessBox("记忆编织器 (Memory Weaver)", 5.9, 3.0, theme.primary);

  // Down arrow from weaver
  slide.addShape(pres.shapes.LINE, {
    x: 7.4, y: weaverY + boxH, w: 0, h: 0.3,
    line: { color: theme.primary, width: 2 },
    lineEnd: "triangle"
  });

  // Step 3: 生成隐式记忆
  const latentY = weaverY + boxH + 0.3;
  addProcessBox("在潜在空间生成隐式记忆向量", 5.9, 3.0, theme.light, theme.primary);

  // Arrow back left
  slide.addShape(pres.shapes.LINE, {
    x: 1.75, y: latentY + boxH/2, w: 1.75, h: 0,
    line: { color: theme.accent, width: 2, dashType: "dash" },
    lineEnd: "triangle"
  });

  // Step 4 bottom: 记忆注入 → 继续生成
  const injY = latentY + boxH + 0.3;
  addProcessBox("记忆注入 → 推理器继续生成（记忆增强）", 0.5, 3.0, theme.accent);

  // Up arrow back to top (cycle)
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: boxY, w: 0, h: 0,
    line: { color: theme.secondary, width: 1.5, dashType: "dash" }
  });

  // "循环交替" label
  slide.addText("🔄 循环交替 ...", {
    x: 3.8, y: 4.9, w: 2.0, h: 0.3,
    fontSize: 11, fontFace: "Microsoft YaHei",
    color: theme.secondary, align: "center", valign: "middle", italic: true
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("5", {
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
  pres.writeFile({ fileName: "slide-05-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
