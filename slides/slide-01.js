// slide-01.js — Cover Page
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',
  index: 1,
  title: 'Agentic RL: 智能体强化学习'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  
  // Dark background
  slide.background = { color: theme.primary };
  
  // Decorative grid dots pattern (simulated with small shapes)
  const dotPositions = [
    [0.3, 0.3], [0.3, 0.8], [0.3, 1.3], [0.3, 1.8],
    [0.3, 2.3], [0.3, 2.8], [0.3, 3.3], [0.3, 3.8],
    [0.3, 4.3], [0.3, 4.8],
    [9.3, 0.3], [9.3, 0.8], [9.3, 1.3], [9.3, 1.8],
    [9.3, 2.3], [9.3, 2.8], [9.3, 3.3], [9.3, 3.8],
    [9.3, 4.3], [9.3, 4.8],
  ];
  dotPositions.forEach(([x, y]) => {
    slide.addShape(pres.shapes.OVAL, {
      x: x, y: y, w: 0.04, h: 0.04,
      fill: { color: theme.accent, transparency: 60 }
    });
  });
  
  // Top accent line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.04,
    fill: { color: theme.accent }
  });
  
  // Left decorative bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 2.2, w: 0.06, h: 1.6,
    fill: { color: theme.accent }
  });
  
  // Main title
  slide.addText("Agentic RL", {
    x: 0.8, y: 1.8, w: 8.5, h: 1.0,
    fontSize: 54, fontFace: "Georgia",
    color: theme.light, bold: true,
    align: "left", valign: "middle",
    margin: 0
  });
  
  // Subtitle in Chinese
  slide.addText("智能体强化学习", {
    x: 0.8, y: 2.7, w: 8.5, h: 0.7,
    fontSize: 32, fontFace: "Microsoft YaHei",
    color: theme.accent, bold: true,
    align: "left", valign: "middle",
    margin: 0
  });
  
  // Subtitle line
  slide.addText("从传统强化学习到智能体驱动的深度强化学习", {
    x: 0.8, y: 3.4, w: 8.5, h: 0.5,
    fontSize: 16, fontFace: "Microsoft YaHei",
    color: theme.secondary,
    align: "left", valign: "middle",
    margin: 0
  });
  
  // Bottom accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.2, w: 10, h: 0.04,
    fill: { color: theme.accent }
  });
  
  // Date and author info
  slide.addText("2025 · AI & RL", {
    x: 0.8, y: 4.5, w: 4, h: 0.4,
    fontSize: 12, fontFace: "Arial",
    color: theme.secondary,
    align: "left", valign: "middle",
    margin: 0
  });
  
  // Decorative hexagon-like shape (rhombus)
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 8.2, y: 1.0, w: 1.2, h: 1.2,
    fill: { color: theme.accent, transparency: 85 },
    rotate: 45
  });
  
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 8.8, y: 1.6, w: 0.8, h: 0.8,
    fill: { color: theme.accent, transparency: 80 },
    rotate: 45
  });
  
  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = { primary: "000814", secondary: "003566", accent: "ffc300", light: "ffd60a", bg: "001d3d" };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
