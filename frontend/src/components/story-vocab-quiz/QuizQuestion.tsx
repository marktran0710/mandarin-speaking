import { BiLabel } from "../BiLabel";
import { effectiveTierPassCount, tierConfigFromMode, type TierConfig } from "../../utils/quizTiers";
import { CLOZE_BLANK, type VocabQuizMode, type VocabQuizQuestion, type VocabQuizQuestionResult } from "./model";
import { correctAnswer } from "./useQuizSession";
import StudentIcon from "../StudentIcon";

function QuizScoreTrack({ correct, answered, config, totalQuestions }: { correct: number; answered: number; config: TierConfig; totalQuestions: number }) {
  const max = totalQuestions;
  const pass = effectiveTierPassCount(config, totalQuestions);
  const bestPossible = correct + max - answered;
  const reachable = bestPossible >= pass;
  const tierLabel = `${config.tier}-star`;
  const need = pass - correct;
  const pct = (value: number) => `${Math.min(100, (value / max) * 100)}%`;
  return <div className={`vq-track${reachable ? "" : " is-out-of-reach"}`}>
    <div className="vq-track-scale"><span className="vq-track-scale-left"><BiLabel zh={`答對 ${correct}`} pinyin={`Dá duì ${correct}`} en={`${correct} correct`} /></span><span className="vq-track-scale-right"><BiLabel zh={`最多 ${max}`} pinyin={`Zuìduō ${max}`} en={`Max ${max}`} /></span></div>
    <div className="vq-track-rail" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={correct} aria-valuetext={`${correct} correct of ${max}; ${pass} needed for ${config.tier} star${config.tier > 1 ? "s" : ""}`}>
      {bestPossible < max && <span className="vq-track-headroom" style={{ width: pct(bestPossible) }} />}
      <span className="vq-track-fill" style={{ width: pct(correct) }} /><span className="vq-track-notch" style={{ left: pct(pass) }} aria-hidden="true" />
    </div>
    <div className="vq-track-notch-row" aria-hidden="true"><span className="vq-track-notch-label" style={{ left: pct(pass) }}><StudentIcon name="star" size={13} fill="currentColor" /> {pass}</span></div>
    <p className="vq-track-note">{reachable ? need > 0 ? <BiLabel zh={`還要對 ${need} 題`} pinyin={`Hái yào duì ${need} tí`} en={`${need} more correct for ${tierLabel}`} /> : <BiLabel zh="拿到了！" pinyin="Nádào le!" en={`${tierLabel} earned — keep going`} /> : <BiLabel zh={`這次先練習，下次再拿第 ${config.tier} 級`} pinyin={`Zhè cì xiān liànxí, xià cì zài ná dì ${config.tier} jí`} en={`Practice run — try for ${tierLabel} next time`} />}</p>
  </div>;
}

type QuizQuestionProps = {
  question: VocabQuizQuestion; mode: VocabQuizMode | null; selected: string | null;
  results: VocabQuizQuestionResult[]; index: number; questionLimit: number | null;
  requestedQuestionCount: number; isRetryRound: boolean; isLast: boolean; timeLeftMs: number;
  timeLimitMs: number | null; showFinishButton: boolean; onBack?: () => void;
  choose: (option: string) => void; next: () => void; finish: (results: VocabQuizQuestionResult[]) => void;
  speakWord: (text: string) => void;
};

const instructions = {
  translation: ["這是什麼意思？", "Zhè shì shénme yìsi?", "What does this word mean?"], cloze: ["哪個字可以填進去？", "Nǎge zì kěyǐ tián jìnqù?", "Which word fits the blank?"], pinyin: ["這個字怎麼念？", "Zhège zì zěnme niàn?", "How do you read this word?"], pos: ["這是什麼詞類？", "Zhè shì shénme cílèi?", "What part of speech is this?"], synonym: ["哪個字意思一樣？", "Nǎge zì yìsi yíyàng?", "Which word means the same?"], reverse: ["哪個是這個意思？", "Nǎge shì zhège yìsi?", "Which word means this?"], listening: ["聽一聽，選對的字。", "Tīng yi tīng, xuǎn duì de zì.", "Listen and pick the word you hear."],
} as const;

export function QuizQuestion(props: QuizQuestionProps) {
  const { question, mode, selected, results, index, questionLimit, requestedQuestionCount, isRetryRound, isLast, timeLeftMs, timeLimitMs, showFinishButton, onBack, choose, next, finish, speakWord } = props;
  const instruction = instructions[question.kind];
  const optionsLabel = question.kind === "translation" ? `What does ${question.word} mean?` : question.kind === "cloze" ? "Which word fits the blank?" : question.kind === "pinyin" ? `How do you read ${question.word}?` : question.kind === "pos" ? `What part of speech is ${question.word}?` : question.kind === "reverse" ? `Which word means ${question.translation}?` : question.kind === "listening" ? "Which word did you hear?" : `Which word means the same as ${question.word}?`;
  const config = !isRetryRound ? tierConfigFromMode(mode) : null;
  return <section className="story-vocab-quiz vocab-quiz-question-screen" aria-label="Vocabulary quiz">
    <div className="vocab-quiz-topbar">
      {onBack && <button type="button" className="btn-vocab-quiz-back" onClick={onBack}><StudentIcon name="arrow-left" size={16} aria-hidden="true" /><BiLabel zh="回活動" pinyin="Huí huódòng" en="Back to activities" /></button>}
      <div className="vocab-quiz-status-progress">
        <p className="vocab-quiz-progress">{questionLimit !== null ? <BiLabel zh={`第 ${index + 1} / ${questionLimit} 題`} pinyin={`Dì ${index + 1} / ${questionLimit} tí`} en={`Question ${index + 1} of ${questionLimit}`} /> : <BiLabel zh={`第 ${index + 1} 題`} pinyin={`Dì ${index + 1} tí`} en={`Question ${index + 1}`} />}</p>
        {config && <QuizScoreTrack correct={results.filter((result) => result.correct).length} answered={results.length} config={config} totalQuestions={questionLimit ?? config.questionCount} />}
      </div>
      {timeLimitMs !== null && <p className={`vocab-quiz-timer${timeLeftMs <= 10_000 ? " is-low" : ""}`} aria-label={`${Math.ceil(timeLeftMs / 1000)} seconds left`}><StudentIcon name="clock" size={16} aria-hidden="true" /> {Math.ceil(timeLeftMs / 1000)}s</p>}
      {showFinishButton && <button type="button" className="btn-vocab-quiz-finish" onClick={() => finish(results)}><BiLabel zh="結束，看結果" pinyin="Jiéshù, kàn jiéguǒ" en="Finish & see results" /></button>}
    </div>
    <div className="vocab-quiz-content">
      <div className="vocab-quiz-question-panel">
        <div className="vocab-quiz-header"><p className="eyebrow"><BiLabel zh={isRetryRound ? "複習答錯的題目" : "生詞測驗"} pinyin={isRetryRound ? "Fùxí dá cuò de tímù" : "Shēngcí cèyàn"} en={isRetryRound ? "Reviewing missed words" : "Vocabulary Quiz"} /></p>
          <p className="vocab-quiz-instruction"><BiLabel zh={instruction[0]} pinyin={instruction[1]} en={instruction[2]} /></p>
          {question.kind === "cloze" ? <h1 className="vocab-quiz-word vocab-quiz-cloze-sentence">{question.sentenceWithBlank.split(CLOZE_BLANK).map((part, i, parts) => <span key={i}>{part}{i < parts.length - 1 && <span className="vocab-quiz-cloze-blank" aria-hidden="true">{CLOZE_BLANK}</span>}</span>)}<span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question"><StudentIcon name="spark" size={16} aria-hidden="true" /></span></h1> : question.kind === "reverse" ? <h1 className="vocab-quiz-word vocab-quiz-reverse-prompt">{question.translation}</h1> : question.kind === "listening" ? <h1 className="vocab-quiz-word vocab-quiz-listening-prompt"><button type="button" className="btn-vocab-quiz-play" aria-label="Play the word" onClick={() => speakWord(question.correctWord)}><StudentIcon name="volume" size={20} aria-hidden="true" /></button></h1> : <h1 className="vocab-quiz-word">{question.word}{question.isAiGenerated && <span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question"><StudentIcon name="spark" size={16} aria-hidden="true" /></span>}</h1>}
          {questionLimit !== null && requestedQuestionCount > questionLimit && index === 0 && <p className="vocab-quiz-unique-note"><BiLabel zh={`這一輪有 ${questionLimit} 題不重複的題目。`} pinyin={`Zhè yì lún yǒu ${questionLimit} tí bù chóngfù de tímù.`} en={`${questionLimit} unique questions are available for this round.`} /></p>}
        </div>
      </div>
      <div className="vocab-quiz-answer-panel">
        <p className="vocab-quiz-section-label"><BiLabel zh="選出正確答案" pinyin="Xuǎn chū zhèngquè dá'àn" en="Choose the correct answer" /></p>
        <div className={`vocab-quiz-options${question.kind === "pinyin" ? " vocab-quiz-options-pinyin" : ""}`} role="group" aria-label={optionsLabel}>{question.options.map((option) => { const isCorrect = option === correctAnswer(question); const isChosen = option === selected; const state = selected ? isCorrect ? "correct" : isChosen ? "incorrect" : "neutral" : "neutral"; return <button key={option} type="button" className={`vocab-quiz-option vocab-quiz-option-${state}`} onClick={() => choose(option)} disabled={Boolean(selected)} aria-label={state === "correct" ? `${option} (correct answer)` : state === "incorrect" ? `${option} (your answer, incorrect)` : undefined}><span className="vocab-quiz-option-text">{option}</span>{state === "correct" && <StudentIcon name="check-circle" size={18} className="vocab-quiz-option-icon" aria-hidden="true" />}{state === "incorrect" && <StudentIcon name="x-circle" size={18} className="vocab-quiz-option-icon" aria-hidden="true" />}</button>; })}</div>
        <div className="vocab-quiz-actions">{selected && <button type="button" className="btn-vocab-quiz-next" onClick={next}>{isLast ? <BiLabel zh="看結果" pinyin="Kàn jiéguǒ" en="See results" /> : <BiLabel zh="下一題" pinyin="Xià yì tí" en="Next question" />}</button>}</div>
      </div>
    </div>
  </section>;
}
