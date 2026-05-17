// compile-memgen.js — Combine all slides into final MemGen PPTX
const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'MemGen Research';
pres.title = 'MemGen - 生成式隐式记忆论文解读';

const theme = {
  primary: "0a2463",
  secondary: "1e5fa3",
  accent: "3a86ff",
  light: "a8d5ff",
  bg: "e8f4ff"
};

const slideCount = 11;
for (let i = 1; i <= slideCount; i++) {
  const num = String(i).padStart(2, '0');
  const slideModule = require(`./slide-${num}.js`);
  slideModule.createSlide(pres, theme);
}

pres.writeFile({ fileName: "./output/MemGen_Paper_Presentation.pptx" })
  .then(() => console.log("✅ Generated: output/MemGen_Paper_Presentation.pptx"))
  .catch(err => console.error("❌ Error:", err));
