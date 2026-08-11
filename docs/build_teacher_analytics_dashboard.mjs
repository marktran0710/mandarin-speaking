import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const reference = "C:/Users/Administrator/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-analytics-dashboard/assets/reference.xlsx";
const outputDir = new URL("../output/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const outputPath = `${outputDir}teacher-analytics-dashboard.xlsx`;
const previewPath = `${outputDir}teacher-analytics-dashboard-preview.png`;

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(reference));
const sheets = workbook.worksheets;
const dashboard = sheets.getItemAt(0);
// Remove the reference workbook's illustrative marketing numbers before
// populating this learning-measurement version. Preserve its visual system and
// charts, but never present template data as observed student evidence.
dashboard.getRange("A1:Q52").clear({ applyTo: "contents" });
dashboard.getRange("A1").values = [["Mandarin Speaking | Teacher Measurement Dashboard"]];
dashboard.getRange("A2").values = [["Use judged outcomes for learning decisions; keep unjudged audio as a separate system-quality metric."]];
dashboard.getRange("A4:B10").values = [
  ["Metric contract", "Definition"],
  ["Judged mastery pass rate", "Passed pronunciation mastery / attempts with at least one judged syllable"],
  ["Not-enough-evidence rate", "Retry or not_judged attempts / analyzed attempts"],
  ["Average tone accuracy", "Mean backend tone_accuracy across analyzed attempts"],
  ["Average fluency", "Mean backend fluency_score across analyzed attempts"],
  ["Event completeness", "Observed instrumented transitions / expected transitions"],
  ["IRT item usability", "At least 30 responses and no extreme difficulty flag"],
];
dashboard.getRange("A12:B17").values = [
  ["Event", "Required properties"],
  ["practice_started", "studentId, sessionId, topicId, sceneIndex"],
  ["recording_submitted", "attemptId, attemptType, duration"],
  ["analysis_completed", "attemptId, analysisVersion, toneAccuracy, masteryPassed, feedbackQuality"],
  ["feedback_opened", "attemptId, targetWord, feedbackState"],
  ["practice_passed", "attemptId, targetWord, retryCount"],
];
dashboard.getRange("A1:B1").merge();
dashboard.getRange("A1:B1").format = { fill: "#1D6B58", font: { color: "#FFFFFF", bold: true, size: 16 } };
dashboard.getRange("A2:B2").merge();
dashboard.getRange("A2:B2").format = { fill: "#EAF5F0", font: { color: "#355248", italic: true } };
dashboard.getRange("A4:B4").format = { fill: "#D9EEE6", font: { bold: true, color: "#173E35" } };
dashboard.getRange("A12:B12").format = { fill: "#D9EEE6", font: { bold: true, color: "#173E35" } };
dashboard.getRange("A5:B10").format = { fill: "#FFFFFF", font: { color: "#173E35", size: 11 } };
dashboard.getRange("A13:B17").format = { fill: "#FFFFFF", font: { color: "#173E35", size: 11 } };
dashboard.getRange("A4:B17").format.wrapText = true;
dashboard.getRange("A:A").format.columnWidth = 28;
dashboard.getRange("B:B").format.columnWidth = 78;
dashboard.freezePanes.freezeRows(4);
await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: dashboard.name, range: "A1:B17", scale: 1.5, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
