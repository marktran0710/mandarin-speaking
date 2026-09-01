// @ts-nocheck
import { BiLabel } from "../BiLabel";
import StudentIcon from "../StudentIcon";
import PhrasePracticeDrill from "./PhrasePracticeDrill";
import WordProsodyCard from "./WordProsodyCard";
import { toPinyin } from "../../utils/pinyin";

export default function SpeakingResultsPracticeStep({
  hasPhrasePractice,
  allDrillsCleared,
  practiceTargets,
  clearedWords,
  focusKey,
  setFocusKey,
  focusTarget,
  focusWord,
  onDrillPass,
  allPhrasesCleared,
  phrasePracticeItems,
  clearedPhrases,
  phraseFocusIndex,
  setPhraseFocusIndex,
  focusPhrase,
  onPhrasePass,
}) {
  return hasPhrasePractice ? (
    <PhrasePractice {...{ allPhrasesCleared, phrasePracticeItems, clearedPhrases, phraseFocusIndex, setPhraseFocusIndex, focusPhrase, onPhrasePass }} />
  ) : (
    <WordPractice {...{ allDrillsCleared, practiceTargets, clearedWords, focusKey, setFocusKey, focusTarget, focusWord, onDrillPass }} />
  );
}

function WordPractice({ allDrillsCleared, practiceTargets, clearedWords, focusKey, setFocusKey, focusTarget, focusWord, onDrillPass }) {
  return <div className="sfc-step-panel">
    {allDrillsCleared ? <div className="sfc-mastery-banner is-cleared"><p className="sfc-mastery-lead"><StudentIcon name="celebrate" size={18} /> <BiLabel zh="這些字都好了！現在再錄一次整句。" pinyin="Zhèxiē zì dōu hǎo le! Xiànzài zài lù yí cì zhěng jù." en="All words cleared! Now record the whole sentence again." /></p></div> : <p className="sfc-mastery-lead sfc-practice-lead"><StudentIcon name="target" size={18} /> <BiLabel zh="先練好這些字，再錄整句：" pinyin="Xiān liàn hǎo zhèxiē zì, zài lù zhěng jù:" en="First practice these words, then re-record the sentence:" /></p>}
    <div className="sfc-practice-chips">
      {practiceTargets.map((target) => {
        const cleared = Boolean(target.word && clearedWords.includes(target.word.token));
        const current = target.key === focusKey;
        return <button key={target.key} type="button" className={`sfc-mastery-chip sfc-practice-chip ${cleared ? "is-cleared" : "is-pending"}${target.word ? "" : " is-unavailable"}${current ? " is-current" : ""}`} onClick={() => setFocusKey(target.key)} aria-pressed={current}>
          <span className="sfc-practice-chip-word">{target.label} <StudentIcon name={cleared ? "check" : target.word ? "x-circle" : "minus"} size={14} /></span>
          <span className="sfc-practice-chip-pinyin">{target.word ? toPinyin(target.word.token) : "No word-level result"}</span>
        </button>;
      })}
    </div>
    {focusTarget && <><PitchLegend visible={Boolean(focusWord)} /><div className="sfc-focus-word">{focusWord ? <WordProsodyCard key={focusTarget.key} item={focusWord} onDrillPass={onDrillPass} drillDefaultOpen /> : <div className="sfc-practice-unavailable" role="status"><strong>No word-level result / 暫無單字分析</strong><span>{focusTarget.label}</span></div>}</div></>}
  </div>;
}

function PhrasePractice({ allPhrasesCleared, phrasePracticeItems, clearedPhrases, phraseFocusIndex, setPhraseFocusIndex, focusPhrase, onPhrasePass }) {
  return <div className="sfc-step-panel">
    {allPhrasesCleared ? <div className="sfc-mastery-banner is-cleared"><p className="sfc-mastery-lead"><StudentIcon name="celebrate" size={18} /> <BiLabel zh="每個部分都通過了！現在自然地說一次整句。" pinyin="Měi ge bùfen dōu tōngguò le! Xiànzài zìrán de shuō yí cì zhěng jù." en="Every part has passed! Now say the whole sentence naturally." /></p></div> : <p className="sfc-mastery-lead sfc-practice-lead"><StudentIcon name="target" size={18} /> <BiLabel zh="一次練一個部分，藍線是你的音高，虛線是目標形狀。" pinyin="Yí cì liàn yí ge bùfen, lán xiàn shì nǐ de yīngāo, xūxiàn shì mùbiāo xíngzhuàng." en="Practice one part at a time. The blue line is your pitch; the dashed line is the target shape." /></p>}
    <div className="sfc-practice-chips" aria-label="Phrase practice progress">
      {phrasePracticeItems.map((phrase, index) => {
        const cleared = clearedPhrases.includes(phrase);
        return <button key={`${phrase}-${index}`} type="button" className={`sfc-mastery-chip sfc-practice-chip ${cleared ? "is-cleared" : "is-pending"}${index === phraseFocusIndex ? " is-current" : ""}`} onClick={() => setPhraseFocusIndex(index)} aria-pressed={index === phraseFocusIndex}>{phrase} {cleared && <StudentIcon name="check" size={14} />}</button>;
      })}
    </div>
    {focusPhrase && !allPhrasesCleared && <><PitchLegend visible /><div className="sfc-focus-word sfc-focus-phrase"><PhrasePracticeDrill key={focusPhrase} phrase={focusPhrase} onPass={onPhrasePass} /></div></>}
  </div>;
}

function PitchLegend({ visible }) {
  return visible ? <div className="sfc-pronounce-legend mini-contour-legend" aria-hidden="true"><span className="mini-contour-legend-actual"><BiLabel zh="你的音高" en="Your pitch" /></span><span className="mini-contour-legend-reference"><BiLabel zh="目標形狀" en="Target shape" /></span></div> : null;
}
