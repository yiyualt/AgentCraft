// slide-03.js
// Section Divider: "01 背景与概述"
// Bold Center with Split Background — full dark-blue bleed, large centered number

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'section-divider',
  index: 3,
  sectionNumber: '01',
  title: '背景与概述'
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

function makeLineRect(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 }
  };
}

function makeNumberOpts(color) {
  return {
    x: 1.0, y: 0.25, w: 8.0, h: 2.5,
    fontSize: 108, bold: true, align: 'center',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

function makeTitleOpts(color) {
  return {
    x: 0.5, y: 2.95, w: 9.0, h: 1.1,
    fontSize: 40, bold: true, align: 'center',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeIntroOpts(color) {
  return {
    x: 0.5, y: 4.1, w: 9.0, h: 0.6,
    fontSize: 18, bold: false, align: 'center',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeBadgeTextOpts(color) {
  return {
    x: 9.3, y: 5.1, w: 0.5, h: 0.4,
    fontSize: 12, bold: true, align: 'center',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

// ── Slide creation (synchronous — no async/await) ─────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Full-bleed dark blue background
  slide.background = { color: theme.primary };

  // 2. Large semi-transparent oval behind the section number
  var decoOval = makeOval(1.5, 0.15, 7.0, 2.7, theme.accent, 88);
  slide.addShape(pres.shapes.OVAL, decoOval);

  // 3. Section number — very large, centered, accent color
  var numberOpts = makeNumberOpts(theme.accent);
  slide.addText('01', numberOpts);

  // 4. Subtle decorative horizontal line between number and title
  var decoLine = makeLineRect(3.5, 2.75, 3.0, 0.04, theme.accent);
  slide.addShape(pres.shapes.RECTANGLE, decoLine);

  // 5. Thin secondary accent line below the main line for depth
  var decoLine2 = makeLineRect(4.0, 2.82, 2.0, 0.02, theme.light);
  slide.addShape(pres.shapes.RECTANGLE, decoLine2);

  // 6. Section title — bold white
  var titleOpts = makeTitleOpts("FFFFFF");
  slide.addText('背景与概述', titleOpts);

  // 7. Intro line — light accent color
  var introOpts = makeIntroOpts(theme.light);
  slide.addText('大语言模型与自主智能体的发展脉络', introOpts);

  // 8. Page number badge — oval with accent fill and white number
  var badgeOval = makeOval(9.3, 5.1, 0.5, 0.4, theme.accent, 0);
  slide.addShape(pres.shapes.OVAL, badgeOval);

  var badgeTextOpts = makeBadgeTextOpts("FFFFFF");
  slide.addText('3', badgeTextOpts);

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
  pres.writeFile({ fileName: "slide-03-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
