// slide-01.js — Cover Page
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',
  index: 1,
  title: 'MemGen: Weaving Generative Latent Memory for Self-Evolving Agents'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  // Top decorative line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 0.8, w: 2.5, h: 0.06,
    fill: { color: theme.accent }
  });

  // Main title
  slide.addText("MemGen", {
    x: 0.7, y: 1.0, w: 8.6, h: 1.0,
    fontSize: 48, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "left"
  });

  // Subtitle
  slide.addText("Weaving Generative Latent Memory for Self-Evolving Agents", {
    x: 0.7, y: 1.85, w: 8.6, h: 0.6,
    fontSize: 20, fontFace: "Arial",
    color: theme.light, bold: false, align: "left"
  });

  // Chinese subtitle
  slide.addText("生成式隐式记忆 —— 让 Agent 边思考边记忆", {
    x: 0.7, y: 2.5, w: 8.6, h: 0.5,
    fontSize: 18, fontFace: "Microsoft YaHei",
    color: theme.accent, bold: false, align: "left"
  });

  // Bottom decorative line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 3.3, w: 2.5, h: 0.06,
    fill: { color: theme.accent }
  });

  // Author info
  slide.addText("Guibin Zhang, Muxin Fu, Shuicheng Yan", {
    x: 0.7, y: 3.6, w: 8.6, h: 0.4,
    fontSize: 16, fontFace: "Arial",
    color: theme.light, align: "left"
  });

  slide.addText("National University of Singapore (NUS)", {
    x: 0.7, y: 3.95, w: 8.6, h: 0.35,
    fontSize: 14, fontFace: "Arial",
    color: theme.light, align: "left", italic: true
  });

  // Date & code
  slide.addText("2026年5月  |  arXiv:2509.24704  |  github.com/KANABOON1/MemGen", {
    x: 0.7, y: 4.7, w: 8.6, h: 0.4,
    fontSize: 12, fontFace: "Arial",
    color: theme.accent, align: "left"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = { primary: "0a2463", secondary: "1e5fa3", accent: "3a86ff", light: "a8d5ff", bg: "e8f4ff" };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
