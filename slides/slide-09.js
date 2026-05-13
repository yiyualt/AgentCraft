// slide-09.js - Content: Applications & Challenges (Comparison)
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 9,
  title: '应用场景与挑战'
};

const makeCard = (x, y, w, h) => ({
  x, y, w, h,
  fill: { color: "FFFFFF" },
  rectRadius: 0.1,
  shadow: { type: "outer", blur: 4, offset: 2, color: "000000", opacity: 0.08 }
});

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("应用场景与当前挑战", {
    x: 0.5, y: 0.25, w: 9, h: 0.65,
    fontSize: 36, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left", margin: 0
  });

  // === LEFT: Applications ===
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.1, w: 4.2, h: 0.55,
    fill: { color: theme.accent }
  });
  slide.addText("典型应用场景", {
    x: 0.5, y: 1.1, w: 4.2, h: 0.55,
    fontSize: 17, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  const apps = [
    { icon: "01", title: "软件工程", desc: "自动化编码、测试生成、\n代码审查与Bug修复" },
    { icon: "02", title: "数据分析", desc: "自然语言驱动的数据查询、\n可视化与报告自动生成" },
    { icon: "03", title: "科学研究", desc: "文献综述、实验设计、\n假设验证与论文辅助写作" },
    { icon: "04", title: "企业运营", desc: "智能客服、流程自动化、\n决策支持与知识管理" }
  ];

  apps.forEach((app, i) => {
    const y = 1.85 + i * 0.9;

    // Icon/number box
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.7, y: y, w: 0.45, h: 0.45,
      fill: { color: theme.primary },
      rectRadius: 0.06
    });
    slide.addText(app.icon, {
      x: 0.7, y: y, w: 0.45, h: 0.45,
      fontSize: 12, fontFace: "Georgia", color: "FFFFFF",
      bold: true, align: "center", valign: "middle"
    });

    slide.addText(app.title, {
      x: 1.35, y: y - 0.03, w: 3.1, h: 0.3,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true,
      align: "left", valign: "middle", margin: 0
    });

    slide.addText(app.desc, {
      x: 1.35, y: y + 0.27, w: 3.1, h: 0.5,
      fontSize: 10.5, fontFace: "Calibri",
      color: theme.secondary, bold: false,
      align: "left", valign: "top", margin: 0
    });
  });

  // === RIGHT: Challenges ===
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.1, w: 4.3, h: 0.55,
    fill: { color: theme.secondary }
  });
  slide.addText("当前挑战与局限", {
    x: 5.2, y: 1.1, w: 4.3, h: 0.55,
    fontSize: 17, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle"
  });

  const challenges = [
    { title: "幻觉与可靠性", desc: "LLM生成内容的事实准确性\n仍难以保证，影响决策质量" },
    { title: "长程一致性", desc: "多步任务中上下文漂移、\n遗忘与计划偏离问题突出" },
    { title: "安全与对齐", desc: "自主行动可能引发不可预知\n的后果，安全边界难以界定" },
    { title: "成本与效率", desc: "大规模推理的算力消耗与\n响应延迟制约实际部署" }
  ];

  challenges.forEach((ch, i) => {
    const y = 1.85 + i * 0.9;

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 5.4, y: y, w: 0.45, h: 0.45,
      fill: { color: theme.primary },
      rectRadius: 0.06
    });
    slide.addText(String(i + 1), {
      x: 5.4, y: y, w: 0.45, h: 0.45,
      fontSize: 12, fontFace: "Georgia", color: "FFFFFF",
      bold: true, align: "center", valign: "middle"
    });

    slide.addText(ch.title, {
      x: 6.05, y: y - 0.03, w: 3.2, h: 0.3,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true,
      align: "left", valign: "middle", margin: 0
    });

    slide.addText(ch.desc, {
      x: 6.05, y: y + 0.27, w: 3.2, h: 0.5,
      fontSize: 10.5, fontFace: "Calibri",
      color: theme.secondary, bold: false,
      align: "left", valign: "top", margin: 0
    });
  });

  // Vertical divider
  slide.addShape(pres.shapes.LINE, {
    x: 4.85, y: 1.3, w: 0, h: 3.9,
    line: { color: theme.light, width: 1.5 }
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("9", {
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
  pres.writeFile({ fileName: "slide-09-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
