// slide-02.js
// Table of Contents: "目录" — Sidebar Navigation style
// 4 sections with left accent bars, numbers, titles, and descriptions
// Pure Tech Blue color palette, soft & balanced with corner radius 0.08-0.12"

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'toc',
  index: 2,
  title: '目录'
};

// ── Factory helpers (never reuse option objects) ──────────────────────────

function makeOval(x, y, w, h, fillColor, fillTransparency) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor, transparency: fillTransparency },
    line: { color: fillColor, width: 0, transparency: fillTransparency }
  };
}

function makeRect(x, y, w, h, fillColor, fillTransparency) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor, transparency: fillTransparency },
    line: { color: fillColor, width: 0, transparency: fillTransparency }
  };
}

function makeAccentBar(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 },
    rectRadius: 0.03
  };
}

function makeLineRect(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 }
  };
}

function makeTitleOpts(color) {
  return {
    x: 0.7, y: 0.3, w: 5.0, h: 0.75,
    fontSize: 36, bold: true, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeTitleLineOpts(color) {
  return {
    x: 0.7, y: 1.1, w: 8.6, h: 0,
    line: { color: color, width: 1.5 }
  };
}

function makeNumberOpts(x, y, color) {
  return {
    x: x, y: y, w: 0.7, h: 0.65,
    fontSize: 28, bold: true, align: 'left',
    fontFace: 'Georgia', color: color,
    valign: 'middle', margin: 0
  };
}

function makeSectionTitleOpts(x, y, color) {
  return {
    x: x, y: y, w: 7.0, h: 0.4,
    fontSize: 22, bold: true, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'bottom', margin: 0
  };
}

function makeSectionDescOpts(x, y, color) {
  return {
    x: x, y: y, w: 7.0, h: 0.3,
    fontSize: 13, bold: false, align: 'left',
    fontFace: 'Calibri', color: color,
    valign: 'top', margin: 0
  };
}

function makeBadgeOval(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 }
  };
}

function makeBadgeTextOpts(color) {
  return {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, bold: true, align: 'center',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

// ── Data ──────────────────────────────────────────────────────────────────

var sections = [
  {
    num: "01",
    title: "背景与概述",
    desc: "大语言模型与自主智能体的发展脉络"
  },
  {
    num: "02",
    title: "核心架构设计",
    desc: "智能体的记忆、规划与推理机制"
  },
  {
    num: "03",
    title: "关键技术与方法",
    desc: "工具使用、多智能体协作与安全对齐"
  },
  {
    num: "04",
    title: "应用与展望",
    desc: "典型场景、挑战与未来方向"
  }
];

// ── Slide creation (synchronous — no async/await) ─────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Solid background
  slide.background = { color: theme.bg };

  // 2. Decorative geometric shapes (soft & balanced)

  // Large oval — bottom-right corner, secondary color, high transparency
  var decoOval1 = makeOval(6.5, 2.8, 4.5, 3.5, theme.secondary, 90);
  slide.addShape(pres.shapes.OVAL, decoOval1);

  // Medium oval — top-right area, accent color, high transparency
  var decoOval2 = makeOval(7.8, -0.4, 3.2, 2.6, theme.accent, 88);
  slide.addShape(pres.shapes.OVAL, decoOval2);

  // Small oval — top-left corner, light color, moderate transparency
  var decoOval3 = makeOval(-0.6, -0.5, 2.0, 1.8, theme.light, 78);
  slide.addShape(pres.shapes.OVAL, decoOval3);

  // Tiny accent circle — decorative detail near top-right
  var decoOval4 = makeOval(8.9, 0.55, 0.45, 0.45, theme.accent, 55);
  slide.addShape(pres.shapes.OVAL, decoOval4);

  // Tiny primary circle — decorative detail near bottom-left
  var decoOval5 = makeOval(0.3, 4.7, 0.35, 0.35, theme.primary, 65);
  slide.addShape(pres.shapes.OVAL, decoOval5);

  // 3. Top accent edge bar
  var topEdge = makeLineRect(0, 0, 10, 0.05, theme.secondary);
  slide.addShape(pres.shapes.RECTANGLE, topEdge);

  // 4. Page title "目录"
  var titleOpts = makeTitleOpts(theme.primary);
  slide.addText('目录', titleOpts);

  // 5. Decorative line under title
  var titleLine = makeTitleLineOpts(theme.light);
  slide.addShape(pres.shapes.LINE, titleLine);

  // 6. Subtle vertical connecting line on the left (spans all 4 sections)
  var vertLine = makeLineRect(0.73, 1.45, 0.015, 3.28, theme.light);
  slide.addShape(pres.shapes.RECTANGLE, vertLine);

  // 7. Four sections with equal vertical spacing
  var startY = 1.45;
  var spacing = 0.88;
  var accentBarX = 0.7;
  var accentBarW = 0.06;
  var accentBarH = 0.65;
  var numX = 1.0;
  var textX = 1.7;

  sections.forEach(function (sec, i) {
    var y = startY + i * spacing;

    // Left accent bar (RECTANGLE with slight corner radius)
    var bar = makeAccentBar(accentBarX, y, accentBarW, accentBarH, theme.accent);
    slide.addShape(pres.shapes.RECTANGLE, bar);

    // Section number (Georgia, large, accent color)
    var numOpts = makeNumberOpts(numX, y, theme.accent);
    slide.addText(sec.num, numOpts);

    // Section title (Microsoft YaHei, bold, primary color)
    var titleY = y - 0.05;
    var titleOptsSec = makeSectionTitleOpts(textX, titleY, theme.primary);
    slide.addText(sec.title, titleOptsSec);

    // Section description (Calibri, secondary color)
    var descY = y + 0.33;
    var descOpts = makeSectionDescOpts(textX, descY, theme.secondary);
    slide.addText(sec.desc, descOpts);
  });

  // 8. Page number badge — OVAL shape at x:9.3, y:5.1
  var badgeShape = makeBadgeOval(9.3, 5.1, 0.4, 0.4, theme.accent);
  slide.addShape(pres.shapes.OVAL, badgeShape);

  var badgeText = makeBadgeTextOpts('FFFFFF');
  slide.addText('2', badgeText);

  return slide;
}

// ── Standalone preview ────────────────────────────────────────────────────

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
  pres.writeFile({ fileName: "slide-02-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
