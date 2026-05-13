/*
 * slide-04.js — LLM自主智能体核心架构
 * Content Page (Text + Visual, 2x2 Cards)
 * PptxGenJS  |  LAYOUT_16x9 (10" x 5.625")
 * Pure Tech Blue palette  |  No async/await  |  Factory functions only
 */

// ── Slide metadata ──────────────────────────────────────────
var slideConfig = {
  type: 'content',
  index: 4,
  title: 'LLM自主智能体的核心架构'
};

// ── Theme palette (6-char hex without # prefix) ─────────────
var theme = {
  primary: "03045e",
  secondary: "0077b6",
  accent: "00b4d8",
  light: "90e0ef",
  bg: "caf0f8"
};

// ── Card data ───────────────────────────────────────────────
var cards = [
  {
    name: "Profile模块",
    desc: "定义智能体的角色、目标与行为边界，通过角色描述文件引导智能体行为模式",
    x: 0.5, y: 1.3, w: 4.2, h: 1.85
  },
  {
    name: "Memory模块",
    desc: "包含短期记忆（上下文窗口）与长期记忆（向量数据库），实现知识积累与经验复用",
    x: 5.1, y: 1.3, w: 4.4, h: 1.85
  },
  {
    name: "Planning模块",
    desc: "任务分解、子目标生成、多路径推理与自我反思，支持复杂目标的逐步求解",
    x: 0.5, y: 3.4, w: 4.2, h: 1.85
  },
  {
    name: "Action模块",
    desc: "工具调用（API、代码执行、数据库查询）、环境交互与反馈学习",
    x: 5.1, y: 3.4, w: 4.4, h: 1.85
  }
];

// ══════════════════════════════════════════════════════════════
// Factory functions
// Every call returns a fresh object so no reference is ever
// reused across PptxGenJS calls.
// ══════════════════════════════════════════════════════════════

function getBgOpts() {
  return { color: theme.bg };
}

function getTitleOpts() {
  return {
    x: 0.5,
    y: 0.3,
    w: 9.0,
    h: 0.9,
    fontSize: 36,
    bold: true,
    color: theme.primary,
    fontFace: "Microsoft YaHei",
    align: "left",
    margin: 0
  };
}

function getCardShapeOpts(posX, posY, cardW, cardH) {
  return {
    x: posX,
    y: posY,
    w: cardW,
    h: cardH,
    fill: { color: "FFFFFF" },
    rectRadius: 0.1,
    shadow: {
      type: "outer",
      blur: 4,
      offset: 1.5,
      color: "000000",
      opacity: 0.08
    }
  };
}

function getAccentBarOpts(posX, posY) {
  return {
    x: posX,
    y: posY + 0.25,
    w: 0.07,
    h: 1.35,
    fill: { color: theme.accent }
  };
}

function getModuleNameOpts(posX, posY, cardW) {
  return {
    x: posX + 0.3,
    y: posY + 0.2,
    w: cardW - 0.55,
    h: 0.5,
    fontSize: 17,
    bold: true,
    color: theme.primary,
    fontFace: "Microsoft YaHei",
    align: "left",
    valign: "middle",
    margin: 0
  };
}

function getDescOpts(posX, posY, cardW, cardH) {
  return {
    x: posX + 0.3,
    y: posY + 0.75,
    w: cardW - 0.55,
    h: cardH - 0.95,
    fontSize: 12,
    color: theme.secondary,
    fontFace: "Calibri",
    align: "left",
    valign: "top",
    margin: 0
  };
}

function getPageBadgeBgOpts() {
  return {
    x: 9.3,
    y: 5.1,
    w: 0.4,
    h: 0.4,
    fill: { color: theme.accent }
  };
}

function getPageBadgeTextOpts() {
  return {
    x: 9.3,
    y: 5.1,
    w: 0.4,
    h: 0.4,
    fontSize: 12,
    fontFace: "Calibri",
    color: "FFFFFF",
    bold: true,
    align: "center",
    valign: "middle"
  };
}

// ══════════════════════════════════════════════════════════════
// Main entry — synchronous, no async/await
// ══════════════════════════════════════════════════════════════

function createSlide(pres) {
  var slide = pres.addSlide();

  // Background
  slide.background = getBgOpts();

  // Title
  slide.addText("LLM自主智能体的核心架构", getTitleOpts());

  // 2x2 Cards
  cards.forEach(function (card) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, getCardShapeOpts(card.x, card.y, card.w, card.h));
    slide.addShape(pres.shapes.RECTANGLE, getAccentBarOpts(card.x, card.y));
    slide.addText(card.name, getModuleNameOpts(card.x, card.y, card.w));
    slide.addText(card.desc, getDescOpts(card.x, card.y, card.w, card.h));
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, getPageBadgeBgOpts());
  slide.addText("4", getPageBadgeTextOpts());

  return slide;
}

// ══════════════════════════════════════════════════════════════
// Self-test entry point (Node.js)
// ══════════════════════════════════════════════════════════════
if (require.main === module) {
  var pptxgen = require("pptxgenjs");
  var pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  createSlide(pres);
  pres.writeFile({ fileName: "slide-04-preview.pptx" });
}

// ══════════════════════════════════════════════════════════════
// Exports
// ══════════════════════════════════════════════════════════════
module.exports = { createSlide: createSlide, slideConfig: slideConfig, theme: theme, cards: cards };
