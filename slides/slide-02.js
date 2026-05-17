// slide-02.js — Table of Contents
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'toc',
  index: 2,
  title: '目录'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("目录 CONTENTS", {
    x: 0.7, y: 0.5, w: 8.6, h: 0.7,
    fontSize: 32, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });

  // Decorative line under title
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 1.15, w: 1.5, h: 0.05,
    fill: { color: theme.accent }
  });

  const items = [
    { num: "01", title: "研究背景与问题", subtitle: "现有记忆系统两大范式的困境" },
    { num: "02", title: "核心架构", subtitle: "MemGen 双引擎系统详解" },
    { num: "03", title: "实验验证", subtitle: "性能对比与关键发现" },
    { num: "04", title: "总结与展望", subtitle: "贡献、局限与未来方向" }
  ];

  // Layout: 2x2 grid of cards
  const positions = [
    { x: 0.5, y: 1.6 },
    { x: 5.0, y: 1.6 },
    { x: 0.5, y: 3.3 },
    { x: 5.0, y: 3.3 }
  ];

  items.forEach((item, i) => {
    const pos = positions[i];

    // Card background
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: pos.x, y: pos.y, w: 4.2, h: 1.4,
      fill: { color: "FFFFFF" },
      shadow: { type: "outer", blur: 6, offset: 2, color: "CCCCCC", opacity: 0.3 },
      rectRadius: 0.1
    });

    // Number circle
    slide.addShape(pres.shapes.OVAL, {
      x: pos.x + 0.25, y: pos.y + 0.3, w: 0.5, h: 0.5,
      fill: { color: theme.accent }
    });
    slide.addText(item.num, {
      x: pos.x + 0.25, y: pos.y + 0.3, w: 0.5, h: 0.5,
      fontSize: 16, fontFace: "Arial",
      color: "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });

    // Title text
    slide.addText(item.title, {
      x: pos.x + 0.9, y: pos.y + 0.2, w: 3.0, h: 0.4,
      fontSize: 18, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true, align: "left", valign: "middle"
    });

    // Subtitle text
    slide.addText(item.subtitle, {
      x: pos.x + 0.9, y: pos.y + 0.7, w: 3.0, h: 0.4,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "middle"
    });
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("2", {
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
  pres.writeFile({ fileName: "slide-02-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
