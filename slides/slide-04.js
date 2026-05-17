// slide-04.js — Core Innovations
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'content',
  index: 4,
  title: '核心创新'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Title
  slide.addText("MemGen 核心创新", {
    x: 0.5, y: 0.3, w: 9.0, h: 0.6,
    fontSize: 28, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "left"
  });

  // Three cards
  const cards = [
    {
      title: "隐式生成式记忆",
      icon: "🧠",
      items: [
        "在潜在空间动态生成向量",
        "无需外部数据库存储",
        "参数高效（LoRA 适配器）"
      ],
      color: theme.secondary
    },
    {
      title: "记忆-推理交织",
      icon: "🔄",
      items: [
        "推理中实时唤起记忆",
        "标点处触发，流畅自然",
        "非流水线式检索"
      ],
      color: theme.accent
    },
    {
      title: "自发涌现类人记忆",
      icon: "✨",
      items: [
        "规划记忆",
        "程序性记忆",
        "工作记忆"
      ],
      color: theme.primary
    }
  ];

  const cardWidth = 2.8;
  const cardGap = 0.3;
  const startX = 0.5;

  cards.forEach((card, i) => {
    const cx = startX + i * (cardWidth + cardGap);

    // Card background
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: cx, y: 1.3, w: cardWidth, h: 3.6,
      fill: { color: "FFFFFF" },
      shadow: { type: "outer", blur: 8, offset: 3, color: "CCCCCC", opacity: 0.35 },
      rectRadius: 0.15
    });

    // Card top accent bar
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: 1.3, w: cardWidth, h: 0.06,
      fill: { color: card.color }
    });

    // Icon
    slide.addText(card.icon, {
      x: cx, y: 1.5, w: cardWidth, h: 0.5,
      fontSize: 28, align: "center", valign: "middle"
    });

    // Title
    slide.addText(card.title, {
      x: cx + 0.15, y: 2.1, w: cardWidth - 0.3, h: 0.4,
      fontSize: 16, fontFace: "Microsoft YaHei",
      color: card.color, bold: true, align: "center", valign: "middle"
    });

    // Divider line
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx + 0.6, y: 2.55, w: cardWidth - 1.2, h: 0.03,
      fill: { color: theme.light }
    });

    // Items
    const itemText = card.items.map(item => `• ${item}`).join("\n");
    slide.addText(itemText, {
      x: cx + 0.25, y: 2.75, w: cardWidth - 0.5, h: 1.8,
      fontSize: 13, fontFace: "Microsoft YaHei",
      color: theme.secondary, align: "left", valign: "top",
      lineSpacingMultiple: 1.6
    });
  });

  // Page number badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("4", {
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
  pres.writeFile({ fileName: "slide-04-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
