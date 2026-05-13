// slide-01.js
// Cover Page: "基于大语言模型的自主智能体综述"
// Pure Tech Blue color palette, center-aligned layout with geometric decorations

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',
  index: 1,
  title: '基于大语言模型的自主智能体综述'
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

function makeTitleOpts(color) {
  return {
    x: 0.8, y: 1.5, w: 8.4, h: 1.2,
    fontSize: 48, bold: true, align: 'center',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeSubtitleOpts(color) {
  return {
    x: 0.8, y: 3.05, w: 8.4, h: 0.7,
    fontSize: 22, bold: false, align: 'center',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

function makeSupportOpts(color) {
  return {
    x: 0.8, y: 3.8, w: 8.4, h: 0.5,
    fontSize: 16, bold: false, align: 'center',
    fontFace: 'Calibri', color: color,
    valign: 'middle'
  };
}

// ── Slide creation (synchronous — no async/await) ─────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Solid background
  slide.background = { color: theme.bg };

  // 2. Decorative geometric shapes

  // Large oval — top-left corner, secondary color, high transparency
  var shapeOval1 = makeOval(-1.2, -1.0, 4.5, 3.5, theme.secondary, 88);
  slide.addShape(pres.shapes.OVAL, shapeOval1);

  // Large oval — bottom-right corner, accent color, high transparency
  var shapeOval2 = makeOval(6.8, 3.2, 4.5, 3.5, theme.accent, 85);
  slide.addShape(pres.shapes.OVAL, shapeOval2);

  // Medium oval — top-right area, light color, moderate transparency
  var shapeOval3 = makeOval(7.5, -0.6, 3.2, 2.8, theme.light, 75);
  slide.addShape(pres.shapes.OVAL, shapeOval3);

  // Small accent circle — bottom-left decorative dot
  var shapeOval4 = makeOval(0.4, 4.6, 0.7, 0.7, theme.accent, 50);
  slide.addShape(pres.shapes.OVAL, shapeOval4);

  // Small secondary circle — upper decorative dot
  var shapeOval5 = makeOval(8.8, 0.5, 0.55, 0.55, theme.secondary, 50);
  slide.addShape(pres.shapes.OVAL, shapeOval5);

  // Tiny primary circle — accent detail
  var shapeOval6 = makeOval(8.2, 4.3, 0.4, 0.4, theme.primary, 60);
  slide.addShape(pres.shapes.OVAL, shapeOval6);

  // Decorative rectangle bar — top edge accent
  var shapeRect1 = makeRect(0, 0, 10, 0.06, theme.secondary, 0);
  slide.addShape(pres.shapes.RECTANGLE, shapeRect1);

  // Decorative rectangle bar — bottom edge accent
  var shapeRect2 = makeRect(0, 5.55, 10, 0.06, theme.accent, 0);
  slide.addShape(pres.shapes.RECTANGLE, shapeRect2);

  // Left vertical accent strip
  var shapeRect3 = makeRect(0.3, 0, 0.06, 5.625, theme.primary, 70);
  slide.addShape(pres.shapes.RECTANGLE, shapeRect3);

  // 3. Main title
  var titleOpts = makeTitleOpts(theme.primary);
  slide.addText('基于大语言模型的\n自主智能体综述', titleOpts);

  // 4. Decorative horizontal line under title
  var hLine = makeLineRect(3.2, 2.85, 3.6, 0.04, theme.accent);
  slide.addShape(pres.shapes.RECTANGLE, hLine);

  // 5. Subtitle
  var subtitleOpts = makeSubtitleOpts(theme.secondary);
  slide.addText('A Survey of Autonomous Agents\nBased on Large Language Models', subtitleOpts);

  // 6. Supporting text
  var supportOpts = makeSupportOpts(theme.accent);
  slide.addText('从架构设计到应用实践', supportOpts);

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
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
