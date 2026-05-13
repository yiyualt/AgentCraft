// slide-10.js - Summary / Closing Page
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'summary',
  index: 10,
  title: '总结与展望'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  // Decorative large semi-transparent circle top-right
  slide.addShape(pres.shapes.OVAL, {
    x: 6.5, y: -1.5, w: 5.5, h: 5.5,
    fill: { color: theme.secondary, transparency: 55 }
  });

  // Decorative small circle
  slide.addShape(pres.shapes.OVAL, {
    x: -1.0, y: 3.5, w: 2.5, h: 2.5,
    fill: { color: theme.accent, transparency: 65 }
  });

  // Title
  slide.addText("总结与展望", {
    x: 0.5, y: 0.35, w: 9, h: 0.85,
    fontSize: 44, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "left", margin: 0
  });

  // Accent line under title
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 1.25, w: 2.5, h: 0,
    line: { color: theme.accent, width: 3 }
  });

  // Key Takeaways
  const takeaways = [
    { num: "01", text: "LLM自主智能体通过「感知-规划-记忆-行动」四层架构，\n实现了从语言理解到自主任务执行的跨越" },
    { num: "02", text: "多智能体协作框架（AutoGPT、MetaGPT等）正在重新定义\n复杂任务的自动化解决范式" },
    { num: "03", text: "工具使用与长期记忆是提升智能体能力上限的关键技术，\nRAG与函数调用已成为标准组件" },
    { num: "04", text: "安全对齐、幻觉控制与成本优化仍是制约大规模部署的核心\n挑战，需要产学研协同攻关" }
  ];

  takeaways.forEach((item, i) => {
    const y = 1.55 + i * 0.95;

    // Number
    slide.addText(item.num, {
      x: 0.5, y: y, w: 0.6, h: 0.4,
      fontSize: 22, fontFace: "Georgia",
      color: theme.accent, bold: true,
      align: "left", valign: "middle", margin: 0
    });

    // Text
    slide.addText(item.text, {
      x: 1.15, y: y, w: 8, h: 0.85,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: theme.light, bold: false,
      align: "left", valign: "top", margin: 0,
      lineSpacingMultiple: 1.3
    });
  });

  // Bottom tagline
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 5.1, w: 8.5, h: 0,
    line: { color: theme.accent, width: 1, transparency: 50 }
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("10", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: "Calibri",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = {
    primary: "03045e", secondary: "0077b6", accent: "00b4d8",
    light: "90e0ef", bg: "caf0f8"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-10-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
