// slide-11.js — Discussion & Future
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 11,
  title: '思考与展望'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("思考与展望", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Two columns layout

  // Left column: Challenges
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.2, w: 4.3, h: 3.8,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
    rectRadius: 0.15
  });

  // Header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 4.3, h: 0.55,
    fill: { color: theme.secondary }
  });
  slide.addText("⚠️ 挑战与局限", {
    x: 0.5, y: 1.2, w: 4.3, h: 0.55,
    fontSize: 16, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  const challenges = [
    { title: "计算开销", desc: "每个 Token 步骤都可能触发记忆生成，长序列下推理成本仍需关注" },
    { title: "可解释性", desc: "隐式记忆是潜在空间中的向量，属于\"黑盒\"机制，难以解读" },
    { title: "语言适应性", desc: "依赖标点作为语义边界触发，对中文等语言的适应性待验证" },
    { title: "系统复杂度", desc: "与检索式记忆结合的混合架构虽可提升性能，但增加了系统复杂度" }
  ];

  challenges.forEach((item, i) => {
    const sy = 1.9 + i * 0.75;

    slide.addText(item.title, {
      x: 0.8, y: sy, w: 3.8, h: 0.25,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: theme.accent, bold: true, align: "left", valign: "middle"
    });
    slide.addText(item.desc, {
      x: 0.8, y: sy + 0.25, w: 3.8, h: 0.4,
      fontSize: 10, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top"
    });
  });

  // Right column: Future directions
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.2, y: 1.2, w: 4.3, h: 3.8,
    fill: { color: "FFFFFF" },
    shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
    rectRadius: 0.15
  });

  // Header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.2, w: 4.3, h: 0.55,
    fill: { color: theme.accent }
  });
  slide.addText("🚀 未来方向", {
    x: 5.2, y: 1.2, w: 4.3, h: 0.55,
    fontSize: 16, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  const futures = [
    { title: "多语言适配", desc: "扩展标点触发机制，支持中文、日文等非拉丁语系语言的语义边界检测" },
    { title: "混合记忆系统", desc: "将隐式生成式记忆与检索式记忆结合，取长补短，构建更强大的记忆体系" },
    { title: "应用场景探索", desc: "将 MemGen 应用于复杂推理、多轮对话、代码生成等实际场景验证效果" },
    { title: "可解释性改进", desc: "研究如何将隐式记忆向量投射到可理解的语义空间，提升模型透明度" }
  ];

  futures.forEach((item, i) => {
    const sy = 1.9 + i * 0.75;

    slide.addText(item.title, {
      x: 5.5, y: sy, w: 3.8, h: 0.25,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true, align: "left", valign: "middle"
    });
    slide.addText(item.desc, {
      x: 5.5, y: sy + 0.25, w: 3.8, h: 0.4,
      fontSize: 10, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top"
    });
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("11", {
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
  pres.writeFile({ fileName: "slide-11-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
