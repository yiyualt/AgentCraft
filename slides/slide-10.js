// slide-10.js — Summary
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'summary',
  index: 10,
  title: '总结'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  // Title
  slide.addText("总结", {
    x: 0.5, y: 0.4, w: 9.0, h: 0.7,
    fontSize: 36, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "left"
  });

  // Decorative line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.05, w: 1.5, h: 0.05,
    fill: { color: theme.accent }
  });

  const summaryItems = [
    { num: "01", text: '首次提出"隐式生成式记忆"范式创新，在潜在空间中动态生成记忆向量' },
    { num: "02", text: "实现记忆与推理的真正融合——不是检索+推理的流水线，而是推理中随时唤起记忆的循环" },
    { num: "03", text: "参数高效（LoRA适配器），冻结核心LLM，避免灾难性遗忘，保持通用能力" },
    { num: "04", text: "自发涌现类人多层次记忆功能（规划记忆、程序性记忆、工作记忆），无需显式监督" },
    { num: "05", text: "代码已开源：github.com/KANABOON1/MemGen" }
  ];

  summaryItems.forEach((item, i) => {
    const sy = 1.4 + i * 0.75;

    // Number circle
    slide.addShape(pres.shapes.OVAL, {
      x: 0.7, y: sy + 0.05, w: 0.4, h: 0.4,
      fill: { color: theme.accent }
    });
    slide.addText(item.num, {
      x: 0.7, y: sy + 0.05, w: 0.4, h: 0.4,
      fontSize: 12, fontFace: "Arial",
      color: "FFFFFF", bold: true,
      align: "center", valign: "middle"
    });

    // Text
    slide.addText(item.text, {
      x: 1.3, y: sy, w: 8.0, h: 0.5,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: "FFFFFF", align: "left", valign: "middle",
      lineSpacingMultiple: 1.2
    });

    // Subtle separator line
    if (i < summaryItems.length - 1) {
      slide.addShape(pres.shapes.LINE, {
        x: 1.3, y: sy + 0.6, w: 7.8, h: 0,
        line: { color: theme.secondary, width: 0.5 }
      });
    }
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("10", {
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
  pres.writeFile({ fileName: "slide-10-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
