// Screenshots of the voting page (see run.sh): light and dark, phone-sized, at
// 2x. The visitor says yes to three shades first, so both result cards show.
// Environment: PLAYWRIGHT_DIR (where playwright-core is installed), URL (the
// demo server), OUT (the output directory), CHROMIUM (the browser).
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(join(process.env.PLAYWRIGHT_DIR, "package.json"));
const { chromium } = require("playwright-core");

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM, args: ["--no-sandbox"] });
try {
  for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({
      viewport: { width: 420, height: 940 },
      deviceScaleFactor: 2,
      colorScheme: theme,
      hasTouch: true,
    });
    const page = await context.newPage();
    await page.goto(process.env.URL, { waitUntil: "networkidle" });
    for (const key of ["ArrowRight", "ArrowLeft", "ArrowRight", "ArrowRight"]) {
      await page.keyboard.press(key);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
    }
    await page.waitForTimeout(800);
    const name = `screenshot${theme === "dark" ? "-dark" : ""}.png`;
    await page.screenshot({ path: join(process.env.OUT, name) });
    console.log(`wrote ${name}`);
    await context.close();
  }
} finally {
  await browser.close();
}
