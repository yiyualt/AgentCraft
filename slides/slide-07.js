// slide-07.js
// Content Page (Process/Timeline): "规划与推理能力"
// Pure Tech Blue color palette, 4-step process flow with detail cards
// Soft & Balanced style

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 7,
  title: '规划与推理：智能体的核心能力'
};

// ── Step data ────────────────────────────────────────────────────────────────

var steps = [
  {
    num: '01',
    name: '任务分解',
    desc: '将复杂目标拆解为可执行的子任务序列'
  },
  {
    num: '02',
    name: '路径规划',
    desc: '基于状态空间搜索最优执行路径（CoT、ToT等）'
  },
  {
    num: '03',
    name: '动态调整',
    desc: '根据执行反馈实时修正计划与策略'
  },
  {
    num: '04',
    name: '自我反思',
    desc: '对已完成步骤进行回顾评估，优化后续决策'
  }
];

// ── Layout constants ─────────────────────────────────────────────────────────

var BOX_W = 2.1;
var BOX_H = 0.7;
var BOX_Y = 1.2;
var CARD_Y = 2.3;
var CARD_H = 2.7;

var boxX = [0.4, 2.7, 5.0, 7.3];

// ── Factory helpers (never reuse option objects) ────────────────────────────

function makeOval(x, y, w, h, fillColor, fillTransparency) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor, transparency: fillTransparency || 0 },
    line: { color: fillColor, width: 0, transparency: fillTransparency || 0 }
  };
}

function makeRect(x, y, w, h, fillColor, fillTransparency) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor, transparency: fillTransparency || 0 },
    line: { color: fillColor, width: 0, transparency: fillTransparency || 0 }
  };
}

function makeRoundRect(x, y, w, h, fillColor, rectRadius) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 },
    rectRadius: rectRadius || 0.1
  };
}

function makeRoundRectOutline(x, y, w, h, fillColor, lineColor, rectRadius) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { color: lineColor, width: 0.5 },
    rectRadius: rectRadius || 0.1
  };
}

function makeConnector(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 }
  };
}

function makeTitleOpts(color) {
  return {
    x: 0.5, y: 0.3, w: 9.0, h: 0.7,
    fontSize: 36, bold: true, align: 'left',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

function makeStepCircleOpts(x, y) {
  return {
    x: x - 0.2, y: y + 0.15, w: 0.4, h: 0.4,
    fill: { color: "ffffff" },
    line: { color: "ffffff", width: 1.5 }
  };
}

function makeStepNumOpts(x, y, color) {
  return {
    x: x - 0.2, y: y + 0.15, w: 0.4, h: 0.4,
    fontSize: 12, bold: true, align: 'center',
    fontFace: 'Calibri', color: color,
    valign: 'middle'
  };
}

function makeStepNameOpts(x, y, color) {
  return {
    x: x + 0.1, y: y, w: 1.9, h: 0.7,
    fontSize: 16, bold: true, align: 'center',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeCardTitleBar(x, y, color) {
  return {
    x: x, y: y, w: BOX_W, h: 0.06,
    fill: { color: color },
    line: { width: 0 }
  };
}

function makeCardTextOpts(x, y, color) {
  return {
    x: x + 0.15, y: y + 0.2, w: 1.8, h: CARD_H - 0.4,
    fontSize: 11, bold: false, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'top',
    lineSpacing: 18
  };
}

function makePageBadge() {
  return {
    x: 9.3, y: 5.1, w: 0.5, h: 0.35,
    fill: { color: "03045e" },
    line: { width: 0 },
    rectRadius: 0.08
  };
}

function makePageNumOpts() {
  return {
    x: 9.3, y: 5.1, w: 0.5, h: 0.35,
    fontSize: 10, bold: true, align: 'center',
    fontFace: 'Calibri', color: "ffffff",
    valign: 'middle'
  };
}

// ── Slide creation (synchronous — no async/await) ───────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Solid background
  slide.background = { color: theme.bg };

  // 2. Top decorative bar
  var topBar = makeRect(0, 0, 10, 0.05, theme.secondary, 0);
  slide.addShape(pres.shapes.RECTANGLE, topBar);

  // 3. Bottom decorative bar
  var bottomBar = makeRect(0, 5.58, 10, 0.05, theme.accent, 0);
  slide.addShape(pres.shapes.RECTANGLE, bottomBar);

  // 4. Title
  var titleOpts = makeTitleOpts(theme.primary);
  slide.addText('规划与推理：智能体的核心能力', titleOpts);

  // 5. Subtle decorative line under title
  var titleLine = makeRect(0.5, 1.0, 2.0, 0.03, theme.accent, 0);
  slide.addShape(pres.shapes.RECTANGLE, titleLine);

  // 6. Horizontal connecting line behind all step boxes
  var hConnLine = makeRect(0.4, 1.53, 9.0, 0.03, theme.light, 30);
  slide.addShape(pres.shapes.RECTANGLE, hConnLine);

  // 7. Step boxes (top row) — ROUNDED_RECTANGLE with step number circles
  for (var i = 0; i < steps.length; i++) {
    var sx = boxX[i];

    // Step box
    var stepBox = makeRoundRect(sx, BOX_Y, BOX_W, BOX_H, theme.secondary, 0.12);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, stepBox);

    // Step number circle (OVAL on left edge)
    var circle = makeStepCircleOpts(sx, BOX_Y);
    slide.addShape(pres.shapes.OVAL, circle);

    // Step number text inside circle
    var numOpts = makeStepNumOpts(sx, BOX_Y, theme.secondary);
    slide.addText(steps[i].num, numOpts);

    // Step name text inside box
    var nameOpts = makeStepNameOpts(sx, BOX_Y, "ffffff");
    slide.addText(steps[i].name, nameOpts);
  }

  // 8. Connectors between step boxes
  for (var j = 0; j < steps.length - 1; j++) {
    var connectorX = boxX[j] + BOX_W;
    var connectorW = boxX[j + 1] - connectorX;
    var conn = makeConnector(connectorX, 1.52, connectorW, 0.05, theme.accent);
    slide.addShape(pres.shapes.RECTANGLE, conn);

    // Small arrowhead triangle
    var arrow = {
      x: connectorX + connectorW - 0.08, y: 1.48, w: 0.12, h: 0.13,
      fill: { color: theme.accent },
      line: { width: 0 }
    };
    slide.addShape(pres.shapes.RIGHT_ARROW, arrow);
  }

  // 9. Detail cards (bottom row) — white ROUNDED_RECTANGLE cards
  for (var k = 0; k < steps.length; k++) {
    var cx = boxX[k];

    // Card background with subtle border
    var card = makeRoundRectOutline(cx, CARD_Y, BOX_W, CARD_H, "ffffff", theme.light, 0.1);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, card);

    // Colored accent bar at top of card
    var cardBarColors = [theme.secondary, theme.secondary, theme.accent, theme.accent];
    var cardBar = makeCardTitleBar(cx + 0.1, CARD_Y + 0.12, cardBarColors[k]);
    slide.addShape(pres.shapes.RECTANGLE, cardBar);

    // Step number label inside card
    var cardNumOpts = {
      x: cx + 0.15, y: CARD_Y + 0.08, w: 0.5, h: 0.35,
      fontSize: 22, bold: true, align: 'left',
      fontFace: 'Georgia', color: cardBarColors[k],
      valign: 'middle'
    };
    slide.addText(steps[k].num, cardNumOpts);

    // Card subtitle (step name repeated)
    var cardLabelOpts = {
      x: cx + 0.65, y: CARD_Y + 0.08, w: 1.3, h: 0.35,
      fontSize: 13, bold: true, align: 'left',
      fontFace: 'Microsoft YaHei', color: theme.primary,
      valign: 'middle'
    };
    slide.addText(steps[k].name, cardLabelOpts);

    // Detail description text
    var descOpts = makeCardTextOpts(cx, CARD_Y + 0.45, theme.primary);
    slide.addText(steps[k].desc, descOpts);
  }

  // 10. Page number badge
  var badge = makePageBadge();
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, badge);
  var pageNumOpts = makePageNumOpts();
  slide.addText('07', pageNumOpts);

  return slide;
}

// ── Standalone preview ──────────────────────────────────────────────────────

if (require.main === module) {
  var pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  var theme = {
    primary: "03045e",
    secondary: "0077b6",
    accent: "00b4d8",
    light: "90e0ef",
    bg: "caf0f8"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-07-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
