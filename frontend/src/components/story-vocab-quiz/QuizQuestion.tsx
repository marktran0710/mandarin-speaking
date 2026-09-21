import { useEffect, useRef, useState } from "react";
import { BiLabel } from "../ui/BiLabel";
import { effectiveTierPassCount, tierConfigFromMode, type TierConfig } from "../../utils/quizTiers";
import { assessmentAnswerIsCorrect, CLOZE_BLANK, type VocabQuizMode, type VocabQuizQuestion, type VocabQuizQuestionResult } from "./model";
import { correctAnswer } from "./useQuizSession";
import StudentIcon from "../navigation/StudentIcon";
import { StudentQuestionFlow } from "../student-question-flow/StudentQuestionFlow";

// One compact progress rail used by EVERY bounded round. Two rows only: a
// caption ("答對 N / max", plus the ⭐ pass goal when the round has one) and the
// rail itself. `config` is null for rounds with no star threshold (weak-words,
// challenge, retry) — they show the same rail without the notch/goal.
function QuizScoreTrack({ correct, answered, config, totalQuestions }: { correct: number; answered: number; config: TierConfig | null; totalQuestions: number }) {
  const max = totalQuestions;
  const pct = (value: number) => `${max > 0 ? Math.min(100, (value / max) * 100) : 0}%`;
  const pass = config ? effectiveTierPassCount(config, totalQuestions) : null;
  const bestPossible = correct + max - answered;
  const reachable = pass === null || bestPossible >= pass;
  return <div className={`vq-track${reachable ? "" : " is-out-of-reach"}`}>
    <div className="vq-track-scale">
      <span className="vq-track-scale-left"><BiLabel zh={`答對 ${correct} / ${max}`} pinyin={`Dá duì ${correct} / ${max}`} en={`${correct} / ${max} correct`} /></span>
      {pass !== null && <span className="vq-track-scale-goal" title={`${pass} to pass`}><StudentIcon name="star" size={12} fill="currentColor" aria-hidden="true" /> {pass}</span>}
    </div>
    <div className="vq-track-rail" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={correct} aria-valuetext={pass !== null ? `${correct} correct of ${max}; ${pass} needed for ${config!.tier} star${config!.tier > 1 ? "s" : ""}` : `${correct} correct of ${max}`}>
      {pass !== null && bestPossible < max && <span className="vq-track-headroom" style={{ width: pct(bestPossible) }} />}
      <span className="vq-track-fill" style={{ width: pct(correct) }} />
      {pass !== null && <span className="vq-track-notch" style={{ left: pct(pass) }} aria-hidden="true" />}
    </div>
  </div>;
}

type QuizQuestionProps = {
  question: VocabQuizQuestion; mode: VocabQuizMode | null; selected: string | null;
  results: VocabQuizQuestionResult[]; index: number; questionLimit: number | null;
  requestedQuestionCount: number; isRetryRound: boolean; isLast: boolean; timeLeftMs: number;
  timeLimitMs: number | null; showFinishButton: boolean;
  choose: (option: string) => void; next: () => void; finish: (results: VocabQuizQuestionResult[]) => void;
  speakWord: (text: string) => void;
};

const instructions = {
  translation: ["這是什麼意思？", "Zhè shì shénme yìsi?", "What does this word mean?"], cloze: ["哪個字可以填進去？", "Nǎge zì kěyǐ tián jìnqù?", "Which word fits the blank?"], pinyin: ["這個字怎麼念？", "Zhège zì zěnme niàn?", "How do you read this word?"], pos: ["這是什麼詞類？", "Zhè shì shénme cílèi?", "What part of speech is this?"], synonym: ["哪個字意思一樣？", "Nǎge zì yìsi yíyàng?", "Which word means the same?"], reverse: ["哪個是這個意思？", "Nǎge shì zhège yìsi?", "Which word means this?"], listening: ["聽一聽，選對的字。", "Tīng yi tīng, xuǎn duì de zì.", "Listen and pick the word you hear."], assessment: ["完成這一題。", "Wánchéng zhè yì tí.", "Complete this question."],
} as const;

export function QuizQuestion(props: QuizQuestionProps) {
  const { question, mode, selected, results, index, questionLimit, requestedQuestionCount, isRetryRound, isLast, timeLeftMs, timeLimitMs, showFinishButton, choose, next, finish, speakWord } = props;
  const [typedAnswer, setTypedAnswer] = useState("");
  const isAssessment = question.kind === "assessment";
  const isProductiveRecall = isAssessment && question.assessment.answerFormat === "free_text";
  const isPinyinTyping = isAssessment && question.assessment.questionType === "character_to_pinyin_typing";
  // Round 1 (know-it / meaning) may offer a model pronunciation of the target
  // word so a learner can hear it while choosing the meaning. Scoped to the
  // meaning question only — playing the audio on a reverse or pinyin question
  // would give the answer away, and it must never reach Round 2 (typing pinyin).
  const isMeaningQuestion = isAssessment ? question.assessment.questionType === "basic_meaning_mcq" : question.kind === "translation";
  const round1AudioWord = mode === "tier1" && isMeaningQuestion
    ? (isAssessment ? question.assessment.targetWord : question.word)
    : null;
  const nextButtonRef = useRef<HTMLButtonElement>(null);
  const typedAnswerInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => setTypedAnswer(""), [question]);
  // Move focus to the continue button after submission so keyboard users can
  // advance. Deferred a tick: a free-text Enter submits via this same
  // keypress (see the input's onKeyDown below), and focusing the button
  // synchronously moved it under the *same* Enter press — the browser then
  // treated that press as also activating the button, skipping straight past
  // the "Correct!"/"Not quite." feedback to the next question or summary.
  useEffect(() => {
    if (!selected) return;
    const timer = window.setTimeout(() => nextButtonRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [selected]);
  // Focus the free-text input on a fresh typed question so a learner can
  // start typing immediately instead of having to click into the box first.
  useEffect(() => {
    if (isProductiveRecall && !selected) typedAnswerInputRef.current?.focus();
  }, [question, isProductiveRecall, selected]);
  const instruction = instructions[question.kind];
  const optionsLabel = isAssessment ? "Answer choices" : question.kind === "translation" ? `What does ${question.word} mean?` : question.kind === "cloze" ? "Which word fits the blank?" : question.kind === "pinyin" ? `How do you read ${question.word}?` : question.kind === "pos" ? `What part of speech is ${question.word}?` : question.kind === "reverse" ? `Which word means ${question.translation}?` : question.kind === "listening" ? "Which word did you hear?" : `Which word means the same as ${question.word}?`;
  const config = !isRetryRound ? tierConfigFromMode(mode) : null;
  return <StudentQuestionFlow
    ariaLabel="Vocabulary quiz"
    questionKey={index}
    topbar={<>
      <div className="vocab-quiz-status-progress">
        <p className="vocab-quiz-progress">{questionLimit !== null ? <BiLabel zh={`第 ${index + 1} / ${questionLimit} 題`} pinyin={`Dì ${index + 1} / ${questionLimit} tí`} en={`Question ${index + 1} of ${questionLimit}`} /> : <BiLabel zh={`第 ${index + 1} 題`} pinyin={`Dì ${index + 1} tí`} en={`Question ${index + 1}`} />}</p>
        {questionLimit !== null && <QuizScoreTrack correct={results.filter((result) => result.correct).length} answered={results.length} config={config} totalQuestions={questionLimit} />}
      </div>
      {timeLimitMs !== null && <p className={`vocab-quiz-timer${timeLeftMs <= 10_000 ? " is-low" : ""}`} aria-label={`${Math.ceil(timeLeftMs / 1000)} seconds left`}><StudentIcon name="clock" size={16} aria-hidden="true" /> {Math.ceil(timeLeftMs / 1000)}s</p>}
      {showFinishButton && <button type="button" className="btn-vocab-quiz-finish" onClick={() => finish(results)}><BiLabel zh="結束，看結果" pinyin="Jiéshù, kàn jiéguǒ" en="Finish & see results" /></button>}
    </>}
    prompt={<><p className="eyebrow"><BiLabel zh={isRetryRound ? "複習答錯的題目" : "生詞測驗"} pinyin={isRetryRound ? "Fùxí dá cuò de tímù" : "Shēngcí cèyàn"} en={isRetryRound ? "Reviewing missed words" : "Vocabulary Quiz"} /></p>
      <p className="vocab-quiz-instruction"><BiLabel zh={instruction[0]} pinyin={instruction[1]} en={instruction[2]} /></p>
      {isAssessment ? <h1 className="vocab-quiz-word vocab-quiz-assessment-prompt">{question.prompt}</h1> : question.kind === "cloze" ? <h1 className="vocab-quiz-word vocab-quiz-cloze-sentence">{question.sentenceWithBlank.split(CLOZE_BLANK).map((part, i, parts) => <span key={i}>{part}{i < parts.length - 1 && <span className="vocab-quiz-cloze-blank" aria-hidden="true">{CLOZE_BLANK}</span>}</span>)}<span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question"><StudentIcon name="spark" size={16} aria-hidden="true" /></span></h1> : question.kind === "reverse" ? <h1 className="vocab-quiz-word vocab-quiz-reverse-prompt">{question.translation}</h1> : question.kind === "listening" ? <h1 className="vocab-quiz-word vocab-quiz-listening-prompt"><button type="button" className="btn-vocab-quiz-play" aria-label="Play the word" onClick={() => speakWord(question.correctWord)}><StudentIcon name="volume" size={20} aria-hidden="true" /></button></h1> : <h1 className="vocab-quiz-word">{question.word}{question.isAiGenerated && <span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question"><StudentIcon name="spark" size={16} aria-hidden="true" /></span>}</h1>}
      {round1AudioWord && <button type="button" className="btn-vocab-quiz-word-audio" aria-label={`Listen to ${round1AudioWord}`} onClick={() => speakWord(round1AudioWord)}><StudentIcon name="volume" size={18} aria-hidden="true" /> <BiLabel zh="聽發音" pinyin="Tīng fāyīn" en="Listen" /></button>}
      {questionLimit !== null && requestedQuestionCount > questionLimit && index === 0 && <p className="vocab-quiz-unique-note"><BiLabel zh={`這一輪有 ${questionLimit} 題不重複的題目。`} pinyin={`Zhè yì lún yǒu ${questionLimit} tí bù chóngfù de tímù.`} en={`${questionLimit} unique questions are available for this round.`} /></p>}
    </>}
    answers={<><p className="vocab-quiz-section-label"><BiLabel zh={isProductiveRecall ? "寫出正確答案" : "選出正確答案"} pinyin={isProductiveRecall ? "Xiě chū zhèngquè dá'àn" : "Xuǎn chū zhèngquè dá'àn"} en={isProductiveRecall ? "Write the answer" : "Choose the correct answer"} /></p>
      {isProductiveRecall ? <><div className="vocab-quiz-free-text-answer"><input ref={typedAnswerInputRef} type="text" value={typedAnswer} onChange={(event) => setTypedAnswer(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229 && typedAnswer.trim() && !selected) choose(typedAnswer.trim()); }} disabled={Boolean(selected)} aria-label="Your answer" autoComplete="off" placeholder={isPinyinTyping ? "nǐ hǎo · ni3 hao3" : undefined} /><button type="button" className="btn-vocab-quiz-check" onClick={() => choose(typedAnswer.trim())} disabled={!typedAnswer.trim() || Boolean(selected)}><BiLabel zh="檢查答案" pinyin="Jiǎnchá dá'àn" en="Check answer" /></button></div>{isPinyinTyping && <p className="vocab-quiz-pinyin-hint"><BiLabel zh="可以打聲調符號或數字。例如：nǐ hǎo 或 ni3 hao3" pinyin="Kěyǐ dǎ shēngdiào fúhào huò shùzì." en="Type tone marks or numbers — e.g. nǐ hǎo or ni3 hao3." /></p>}</> : <div className={`vocab-quiz-options${question.kind === "pinyin" ? " vocab-quiz-options-pinyin" : ""}`} role="group" aria-label={optionsLabel}>{question.options.map((option) => { const isCorrect = isAssessment ? assessmentAnswerIsCorrect(question, option) : option === correctAnswer(question); const isChosen = option === selected; const state = selected ? isCorrect ? "correct" : isChosen ? "incorrect" : "neutral" : "neutral"; return <button key={option} type="button" className={`vocab-quiz-option vocab-quiz-option-${state}`} onClick={() => choose(option)} disabled={Boolean(selected)} aria-label={state === "correct" ? `${option} (correct answer)` : state === "incorrect" ? `${option} (your answer, incorrect)` : undefined}><span className="vocab-quiz-option-text">{option}</span>{state === "correct" && <StudentIcon name="check-circle" size={18} className="vocab-quiz-option-icon" aria-hidden="true" />}{state === "incorrect" && <StudentIcon name="x-circle" size={18} className="vocab-quiz-option-icon" aria-hidden="true" />}</button>; })}</div>}
      {selected && isAssessment && <div className="vocab-quiz-assessment-feedback"><p className={assessmentAnswerIsCorrect(question, selected) ? "is-correct" : "is-incorrect"}>{assessmentAnswerIsCorrect(question, selected) ? "Correct!" : "Not quite."}</p>{!assessmentAnswerIsCorrect(question, selected) && isProductiveRecall && <p>Correct answer: <strong>{question.correctAnswer}</strong></p>}<p>{question.explanation}</p></div>}
    </>}
    actions={selected ? <button ref={nextButtonRef} type="button" className="btn-vocab-quiz-next" onClick={next}>{isLast ? <BiLabel zh="看結果" pinyin="Kàn jiéguǒ" en="See results" /> : <BiLabel zh="下一題" pinyin="Xià yì tí" en="Next question" />}</button> : null}
  />;
}
