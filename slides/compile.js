// compile.js — Combine all slides into final PPTX
const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'AgenTracer Research';
pres.title = 'AgenTracer - 论文解读';

const theme = {
  primary: "03045e",
  secondary: "0077b6",
  accent: "00b4d8",
  light: "90e0ef",
  bg: "caf0f8"
};

for (let i = 1; i <= 12; i++) {
  const num = String(i).padStart(2, '0');
  const slideModule = require(`./slide-${num}.js`);
  slideModule.createSlide(pres, theme);
}

pres.writeFile({ fileName: "./output/AgenTracer-论文解读.pptx" })
  .then(() => console.log("✅ Generated: output/AgenTracer-论文解读.pptx"))
  .catch(err => console.error("❌ Error:", err));
