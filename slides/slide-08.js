// slide-08.js — Emergent Human-like Memory
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 8,
  title: '自发涌现类人记忆'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("关键发现：自发涌现的类人记忆", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  slide.addText("通过聚类分析隐式记忆的潜在表示，发现无监督下自发涌现的三种记忆类型", {
    x: 0.5, y: 0.85, w: 9.0, h: 0.35,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary, align: "left"
  });

  // Three large cards
  const cards = [
    {
      title: "🗺️ 规划记忆",
      description: "存储任务规划和策略",
      effect: "移除后规划失败率大增",
      color: theme.primary,
      iconBg: theme.accent
    },
    {
      title: "🔧 程序性记忆",
      description: "存储工具使用流程",
      effect: "移除后工具调用错误增多",
      color: theme.secondary,
      iconBg: theme.accent
    },
    {
      title: "💭 工作记忆",
      description: "保持任务上下文一致性",
      effect: "移除后任务误解增多",
      color: theme.accent,
      iconBg: theme.primary
    }
  ];

  const cardW = 2.85;
  const gap = 0.25;
  const startX = 0.45;

  cards.forEach((card, i) => {
    const cx = startX + i * (cardW + gap);

    // Card bg
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.5, w: cardW, h: 3.2,
      fill: { color: "FFFFFF" },
      shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
      rectRadius: 0.15
    });

    // Top accent bar
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: 1.5, w: cardW, h: 0.55,
      fill: { color: card.color }
    });

    // Icon circle
    slide.addShape(pres.shapes.OVAL, {
      x: cx + 0.15, y: 1.58, w: 0.4, h: 0.4,
      fill: { color: "FFFFFF" }
    });
    slide.addText(card.title.split(" ")[0], {
      x: cx + 0.15, y: 1.58, w: 0.4, h: 0.4,
      fontSize: 14, align: "center", valign: "middle"
    });

    // Title text
    slide.addText(card.title, {
      x: cx + 0.65, y: 1.58, w: 2.0, h: 0.4,
      fontSize: 14, fontFace: "Microsoft YaHei",
      color: "FFFFFF", bold: true, align: "left", valign: "middle"
    });

    // Content
    slide.addText("功能", {
      x: cx + 0.3, y: 2.3, w: cardW - 0.6, h: 0.3,
      fontSize: 11, fontFace: "Microsoft YaHei",
      color: theme.accent, bold: true, align: "left", valign: "middle"
    });
    slide.addText(card.description, {
      x: cx + 0.3, y: 2.6, w: cardW - 0.6, h: 0.5,
      fontSize: 13, fontFace: "Microsoft YaHei",
      color: theme.primary, align: "left", valign: "top"
    });

    // Divider
    slide.addShape(pres.shapes.LINE, {
      x: cx + 0.3, y: 3.2, w: cardW - 0.6, h: 0,
      line: { color: theme.light, width: 1 }
    });

    slide.addText("移除影响", {
      x: cx + 0.3, y: 3.3, w: cardW - 0.6, h: 0.3,
      fontSize: 11, fontFace: "Microsoft YaHei",
      color: theme.accent, bold: true, align: "left", valign: "middle"
    });
    slide.addText(card.effect, {
      x: cx + 0.3, y: 3.6, w: cardW - 0.6, h: 0.5,
      fontSize: 13, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top"
    });
  });

  // Bottom annotation
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 2.5, y: 4.9, w: 5.0, h: 0.4,
    fill: { color: theme.light },
    rectRadius: 0.08
  });
  slide.addText("⭐ 无需显式监督，自发涌现 — 暗示通向更自然机器认知的路径", {
    x: 2.5, y: 4.9, w: 5.0, h: 0.4,
    fontSize: 12, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "center", valign: "middle"
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("8", {
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
  pres.writeFile({ fileName: "slide-08-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
