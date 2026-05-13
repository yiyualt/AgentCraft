// compile.js - Compile all slides into final PPTX
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "AI Survey";
pres.title = "基于大语言模型的自主智能体综述";

const theme = {
  primary: "03045e",
  secondary: "0077b6",
  accent: "00b4d8",
  light: "90e0ef",
  bg: "caf0f8"
};

for (let i = 1; i <= 10; i++) {
  const num = String(i).padStart(2, "0");
  const slideModule = require(`./slide-${num}.js`);
  slideModule.createSlide(pres, theme);
}

pres.writeFile({ fileName: "./output/presentation.pptx" }).then(() => {
  console.log("Presentation saved to output/presentation.pptx");
});
