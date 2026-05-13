// slide-05.js
// Content Page (Comparison): "主流自主智能体框架对比"
// Table + Highlights layout with modern styled comparison table
// Pure Tech Blue color palette

const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 5,
  title: '主流自主智能体框架对比'
};

// ── Factory helpers (never reuse option objects) ──────────────────────────

function makeTitleOpts(color) {
  return {
    x: 0.5, y: 0.35, w: 9.0, h: 0.85,
    fontSize: 36, bold: true, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makeSeparatorOpts(x, y, w, h, color) {
  return {
    x: x, y: y, w: w, h: h,
    fill: { color: color },
    line: { width: 0 }
  };
}

function makeTableOpts(x, y, w, colW, rowH) {
  return {
    x: x, y: y, w: w,
    colW: colW,
    rowH: rowH,
    margin: [0.08, 0.12, 0.08, 0.12],
    border: { type: "solid", pt: 0.5, color: "caf0f8" },
    align: "left",
    valign: "middle",
    fontFace: "Calibri",
    fontSize: 11
  };
}

function makeCellOpts(fontSize, bold, color, fillColor) {
  return {
    fontSize: fontSize,
    bold: bold,
    color: color,
    fill: { color: fillColor },
    fontFace: "Calibri",
    align: "left",
    valign: "middle"
  };
}

function makeCellOptsZh(fontSize, bold, color, fillColor) {
  return {
    fontSize: fontSize,
    bold: bold,
    color: color,
    fill: { color: fillColor },
    fontFace: "Microsoft YaHei",
    align: "left",
    valign: "middle"
  };
}

function makeSummaryOpts(color) {
  return {
    x: 0.5, y: 4.4, w: 9.0, h: 0.55,
    fontSize: 12, bold: false, align: 'left',
    fontFace: 'Microsoft YaHei', color: color,
    valign: 'middle'
  };
}

function makePageBadgeOpts(color, bgColor) {
  return {
    x: 9.3, y: 5.1, w: 0.55, h: 0.35,
    fontSize: 10, bold: true, align: 'center',
    fontFace: 'Calibri', color: color,
    valign: 'middle',
    fill: { color: bgColor },
    rectRadius: 0.08
  };
}

// ── Data ──────────────────────────────────────────────────────────────────

var tableHeaders = ["框架", "核心特点", "典型应用", "开源状态"];

var tableRows = [
  ["AutoGPT", "任务分解与自循环执行", "通用任务自动化", "开源"],
  ["MetaGPT", "多智能体SOP协作", "软件工程协作", "开源"],
  ["BabyAGI", "优先级驱动的任务管理", "任务调度与执行", "开源"],
  ["LangGraph", "图结构控制流", "复杂Agent工作流", "开源"],
  ["CrewAI", "角色化多智能体编排", "团队协作模拟", "开源"]
];

var summaryText = "当前主流框架均聚焦于任务分解与协作编排，差异化体现在SOP约束与多智能体通信机制";

// ── Slide creation (synchronous — no async/await) ─────────────────────────

function createSlide(pres, theme) {
  var slide = pres.addSlide();

  // 1. Solid background
  slide.background = { color: theme.bg };

  // 2. Title
  var titleOpts = makeTitleOpts(theme.primary);
  slide.addText("主流自主智能体框架对比", titleOpts);

  // 3. Title underline separator
  var sep = makeSeparatorOpts(0.5, 1.15, 1.8, 0.04, theme.accent);
  slide.addShape(pres.shapes.RECTANGLE, sep);

  // 4. Table
  var colW = [1.4, 3.0, 2.8, 2.0];
  var rowH = [0.5, 0.42, 0.42, 0.42, 0.42, 0.42];
  var tableOpts = makeTableOpts(0.4, 1.4, 9.2, colW, rowH);

  var tableData = [];
  // Header row styled with arrays for per-cell styling
  // Row 0: Header
  var headerRow = tableHeaders.map(function (text) {
    return { text: text, options: makeCellOptsZh(13, true, "FFFFFF", theme.primary) };
  });
  tableData.push(headerRow);

  // Data rows with alternating backgrounds
  var altColors = [theme.bg, "FFFFFF"];
  for (var i = 0; i < tableRows.length; i++) {
    var row = tableRows[i];
    var bgColor = altColors[i % 2];
    var dataRow = row.map(function (text, j) {
      if (j === 0) {
        return { text: text, options: makeCellOpts(11, true, theme.secondary, bgColor) };
      }
      return { text: text, options: makeCellOptsZh(11, false, theme.secondary, bgColor) };
    });
    tableData.push(dataRow);
  }

  slide.addTable(tableData, tableOpts);

  // 5. Summary text below table
  var summaryOpts = makeSummaryOpts(theme.primary);
  slide.addText(summaryText, summaryOpts);

  // 6. Page number badge
  var badgeOpts = makePageBadgeOpts("FFFFFF", theme.primary);
  slide.addText("5", badgeOpts);

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
  pres.writeFile({ fileName: "slide-05-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
