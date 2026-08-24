import type { ReactNode } from "react";
import { BiLabel, BiText } from "../../components/BiLabel";
import type { WordProsody } from "./types";

export function ScriptWordLevel({ transcription, wordProsody = [] }: { transcription: string; wordProsody?: WordProsody[] }) {
  const scriptWords = wordProsody.length > 0
    ? wordProsody.map((word, index) => ({ token: word.token, index: word.index ?? index, contour: word.contour_shape, feedback: word.feedback, meanPitch: word.mean_pitch, pitchRange: word.pitch_range }))
    : tokenizeTranscript(transcription).map((token, index) => ({ token, index, contour: "", feedback: "", meanPitch: 0, pitchRange: 0 }));
  if (scriptWords.length === 0) return <div className="voice-script-empty"><BiText zh="音檔轉錄完成後，會顯示逐字稿。" pinyin="Yīndǎng zhuǎnlù wánchéng hòu, huì xiǎnshì zhúzì gǎo." en="Word-level script appears after audio transcription." /></div>;
  return <div className="voice-script-level" aria-label="Word-level script">{scriptWords.map((word) => <span className="voice-script-token" key={`${word.token}-${word.index}`} title={word.feedback || undefined}><strong lang="zh-Hant">{word.token}</strong>{word.contour && <em><BiLabel {...formatContourShape(word.contour)} /></em>}{word.meanPitch > 0 && <small>{Math.round(word.meanPitch)} Hz / {Math.round(word.pitchRange)} Hz</small>}</span>)}</div>;
}

export function ScoreCard({ label, value }: { label: ReactNode; value: string }) {
  return <div className="voice-score-card"><span>{label}</span><strong>{value}</strong></div>;
}

export function ModelExampleCard({ text, focusWord }: { text: string; focusWord?: string }) {
  const exampleText = text.trim() || "今天下雨，所以我帶傘。";
  const playExample = () => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(exampleText);
    utterance.lang = "zh-TW"; utterance.rate = 0.82; utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  };
  return <section className="voice-model-example" aria-label="100 score example"><div><span><BiLabel zh="滿分示範" pinyin="Mǎnfēn shìfàn" en="100-score example" /></span><h2><BiLabel zh="先聽，再用你的聲音跟著說" pinyin="Xiān tīng, zài yòng nǐ de shēngyīn gēnzhe shuō" en="Listen, then copy with your voice" /></h2><p lang="zh-Hant">{exampleText}</p></div><div className="voice-model-example-actions">{focusWord && <em><BiLabel zh={`先練：${focusWord}`} en={`Focus first: ${focusWord}`} /></em>}<button type="button" onClick={playExample}><BiLabel zh="播放示範" pinyin="Bòfàng shìfàn" en="Play example" /></button></div></section>;
}

export function StudentFeedbackCards({ toneAccuracy, fluencyScore, speechRate, wordProsody }: { toneAccuracy: number; fluencyScore: number; speechRate: number; wordProsody: WordProsody[] }) {
  const focus = getToneFocusItems(wordProsody)[0];
  const strength = studentStrength(toneAccuracy, fluencyScore);
  const fix = studentFix(toneAccuracy, fluencyScore, speechRate, focus);
  const next = studentNextStep(speechRate, focus);
  const cards = [["good", "優點", "Yōudiǎn", "Good", strength], ["fix", "待改進", "Dài gǎijìn", "Fix", fix], ["next", "下次試試", "Xiàcì shìshi", "Next try", next]] as const;
  return <section className="voice-student-feedback" aria-label="Student feedback">{cards.map(([className, zh, pinyin, en, line]) => <div className={`voice-student-feedback-card ${className}`} key={className}><span><BiLabel zh={zh} pinyin={pinyin} en={en} /></span><strong><BiText zh={line.zh} pinyin={line.pinyin} en={line.en} /></strong></div>)}</section>;
}

export function FeedbackBlock({ title, score, text }: { title: ReactNode; score: number; text: string }) {
  return <div className="feedback-block"><strong>{title} · {Math.round(score)}/100</strong><p>{text}</p></div>;
}

export function getToneFocusItems(items: WordProsody[]): WordProsody[] {
  const focus = items.map((item) => ({ item, score: (item.contour_shape === "variable" ? 3 : 0) + (item.pitch_range < 15 ? 2 : 0) + (item.pitch_range > 95 ? 1 : 0) })).filter((entry) => entry.score > 0).sort((a, b) => b.score - a.score).map((entry) => entry.item).slice(0, 4);
  return focus.length > 0 ? focus : items.slice(0, 4);
}

export function formatContourShape(shape: string): { zh: string; en: string } {
  const labels: Record<string, { zh: string; en: string }> = { dip: { zh: "凹型", en: "Dipping" }, falling: { zh: "下降", en: "Falling" }, level: { zh: "平", en: "Level" }, rising: { zh: "上升", en: "Rising" }, variable: { zh: "不穩定", en: "Variable" } };
  return labels[shape] || labels.variable;
}

function tokenizeTranscript(transcription: string): string[] { return transcription.match(/[\u4e00-\u9fff]|[A-Za-z0-9']+/g)?.slice(0, 80) || []; }
interface BilingualLine { zh: string; pinyin?: string; en: string; }
function studentStrength(toneAccuracy: number, fluencyScore: number): BilingualLine {
  if (toneAccuracy >= 80 && fluencyScore >= 75) return { zh: "你的聲調和節奏已經夠清楚，可以試著說更長的句子了。", pinyin: "Nǐ de shēngdiào hé jiézòu yǐjīng gòu qīngchǔ, kěyǐ shìzhe shuō gèng cháng de jùzi le.", en: "Your tones and rhythm are clear enough to build a longer sentence." };
  if (toneAccuracy >= 75) return { zh: "你的聲調形狀聽得出來。", pinyin: "Nǐ de shēngdiào xíngzhuàng tīng de chūlái.", en: "Your tone shape is recognizable." };
  if (fluencyScore >= 75) return { zh: "你說話的節奏很穩定。", pinyin: "Nǐ shuōhuà de jiézòu hěn wěndìng.", en: "Your speaking rhythm is steady." };
  return { zh: "你完成了一次錄音，現在來改進一個小地方吧。", pinyin: "Nǐ wánchéng le yí cì lùyīn, xiànzài lái gǎijìn yí gè xiǎo dìfāng ba.", en: "You completed a recording. Now improve one small part." };
}
function studentFix(toneAccuracy: number, fluencyScore: number, speechRate: number, focus?: WordProsody): BilingualLine {
  if (speechRate > 6.5) return { zh: "說慢一點，讓每個聲調都有時間發完整。", pinyin: "Shuō màn yìdiǎn, ràng měi gè shēngdiào dōu yǒu shíjiān fā wánzhěng.", en: "Slow down so each Mandarin tone has time to finish." };
  if (toneAccuracy < 65 && focus) return { zh: `把「${focus.token}」的聲調變化說得更清楚一點。`, en: `Make the tone movement clearer on "${focus.token}".` };
  if (fluencyScore < 60) return { zh: "把字跟字連得更順一點，不要每個字中間都停頓。", pinyin: "Bǎ zì gēn zì lián de gèng shùn yìdiǎn, búyào měi gè zì zhōngjiān dōu tíngdùn.", en: "Connect the words more smoothly without stopping between every character." };
  if (focus) return { zh: `先把「${focus.token}」練熟一點。`, en: `Polish "${focus.token}" first.` };
  return { zh: "句子保持簡短，把每個聲調都說清楚。", pinyin: "Jùzi bǎochí jiǎnduǎn, bǎ měi gè shēngdiào dōu shuō qīngchǔ.", en: "Keep the sentence short and make every tone clear." };
}
function studentNextStep(speechRate: number, focus?: WordProsody): BilingualLine {
  if (focus) return { zh: `把「${focus.token}」說三次，再說一次完整的句子。`, en: `Say "${focus.token}" three times, then repeat the full sentence.` };
  if (speechRate < 2.5) return { zh: "再說一次同一句話，試著說得更順一點。", pinyin: "Zài shuō yí cì tóng yí jù huà, shìzhe shuō de gèng shùn yìdiǎn.", en: "Try the same sentence again with a little more flow." };
  return { zh: "再錄一次，試著保持一樣清楚的節奏。", pinyin: "Zài lù yí cì, shìzhe bǎochí yíyàng qīngchǔ de jiézòu.", en: "Record again and try to match the same clear rhythm." };
}
