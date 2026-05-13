// slide-06.js
// Section Divider: "关键技术与方法"
// Pure Tech Blue color palette, left-aligned layout with accent block

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'section-divider',
  index: 6,
  title: '关键技术与方法'
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

function makeBadgeOval(x, y, w, h, fillColor) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor },
    line: { width: 0 }
  };
}

function makeSectionNumberOpts(color) {
  return {
    x: 2.2, y: 1.2, w: 5.5, h: 1.4,
    fontSize: 108, bold: true, align: 'left',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

function makeSectionTitleOpts(color) {
  return {
    x: 2.2, y: 3.0, w: 6.5, h: 0.8,
    fontSize: 40, bold: true, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeIntroLineOpts(color) {
  return {
    x: 2.2, y: 3.7, w: 6.5, h: 0.5,
    fontSize: 18, bold: false, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makePageNumberOpts(color) {
  return {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 11, bold: true, align: 'center',
    fontFace: 'Georgia', color: color,
    valign: 'middle'
  };
}

// ── Slide creation (synchronous — no async/await) ─────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Full-bleed dark blue background (theme.secondary)
  slide.background = { color: theme.secondary };

  // 2. Left accent block — large vertical rectangle
  var accentBlock = makeRect(0, 0, 1.6, 5.625, theme.primary, 0);
  slide.addShape(pres.shapes.RECTANGLE, accentBlock);

  // 3. Decorative OVAL shapes inside the accent block (transparent)

  // Small decorative circle — top area
  var decoOval1 = makeOval(0.35, 0.4, 0.5, 0.5, theme.accent, 65);
  slide.addShape(pres.shapes.OVAL, decoOval1);

  // Medium decorative circle — middle area
  var decoOval2 = makeOval(0.15, 2.5, 0.7, 0.7, theme.light, 75);
  slide.addShape(pres.shapes.OVAL, decoOval2);

  // Small decorative circle — lower area
  var decoOval3 = makeOval(0.5, 4.6, 0.35, 0.35, theme.accent, 70);
  slide.addShape(pres.shapes.OVAL, decoOval3);

  // Tiny accent dot — near bottom
  var decoOval4 = makeOval(0.8, 4.0, 0.2, 0.2, theme.light, 60);
  slide.addShape(pres.shapes.OVAL, decoOval4);

  // 4. Thin horizontal LINE above the title (accent color)
  var accentLine = makeLineRect(2.2, 2.55, 5.5, 0.04, theme.accent);
  slide.addShape(pres.shapes.RECTANGLE, accentLine);

  // 5. Section number "02"
  var sectionNumberOpts = makeSectionNumberOpts(theme.accent);
  slide.addText('02', sectionNumberOpts);

  // 6. Section title "关键技术与方法"
  var sectionTitleOpts = makeSectionTitleOpts('FFFFFF');
  slide.addText('关键技术与方法', sectionTitleOpts);

  // 7. Intro line
  var introLineOpts = makeIntroLineOpts(theme.light);
  slide.addText('规划推理、工具使用与多智能体协作', introLineOpts);

  // 8. Page number badge
  var badgeShape = makeBadgeOval(9.3, 5.1, 0.4, 0.4, theme.accent);
  slide.addShape(pres.shapes.OVAL, badgeShape);

  var pageNumberOpts = makePageNumberOpts('FFFFFF');
  slide.addText('6', pageNumberOpts);

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
  pres.writeFile({ fileName: "slide-06-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
