import { useEffect, useMemo, useState } from "react";
import Icon from "../shared/ui/Icon";
import { deleteQuizVocabularyWord, listVocabularyStories } from "../services/api/vocabulary";
import type { StoredCustomStory } from "../services/api/stories-submissions";
import { buildVocabularyInventory, matchesVocabularySearch, vocabularyEntriesToCsv, type VocabularyEntry } from "./admin-vocabulary/model";
import { vocabularyBookSource } from "./admin-vocabulary/book-sources";
import VocabularyEditor from "./admin-vocabulary/VocabularyEditor";
import QuestionPreview from "./admin-vocabulary/QuestionPreview";
import "./admin-vocabulary/styles.css";

const PAGE_SIZE = 30;

export default function AdminVocabularyPage({ refreshKey = 0, onOpenMaterials }: { refreshKey?: number; onOpenMaterials?: () => void }) {
  const [stories, setStories] = useState<StoredCustomStory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [lesson, setLesson] = useState("5-8");
  const [storyId, setStoryId] = useState("");
  const [review, setReview] = useState("");
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<VocabularyEntry | null>(null);
  const [previewing, setPreviewing] = useState<VocabularyEntry | null>(null);
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void listVocabularyStories().then(rows => {
      if (active) setStories(rows);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : "Could not load vocabulary.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload, refreshKey]);

  const inventory = useMemo(() => buildVocabularyInventory(stories), [stories]);
  const lessons = useMemo(() => [...new Set(stories.map(s => s.lessonNumber).filter((n): n is number => n != null))].sort((a, b) => a - b), [stories]);
  const inLesson = (number: number | null | undefined) => lesson === "" || (lesson === "5-8" ? number != null && number >= 5 && number <= 8 : String(number ?? null) === lesson);
  const availableStories = stories.filter(story => inLesson(story.lessonNumber));
  const filtered = inventory.filter(entry => inLesson(entry.lessonNumber)
    && (!storyId || entry.storyId === storyId)
    && matchesVocabularySearch(entry, query)
    && (review !== "unverified" || !vocabularyBookSource(entry))
    && (review !== "missing" || !entry.pinyin || !entry.translation || !entry.pos));
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const uniqueWords = new Set(filtered.map(entry => entry.word)).size;
  const selectedStory = stories.find(story => story.id === storyId);
  const newQuizEntry: VocabularyEntry | null = selectedStory ? {
    word: "", pinyin: "", translation: "", pos: "", id: JSON.stringify([selectedStory.id, "quiz-assessment", "new"]),
    storyId: selectedStory.id, storyTitle: selectedStory.title, lessonNumber: selectedStory.lessonNumber ?? null,
    lessonSubOrder: selectedStory.lessonSubOrder ?? null, frameIndex: 0,
    wordIndex: new Set((selectedStory.vocabAssessment ?? []).map(question => question.wordId)).size,
    storyWide: false, source: "quiz-assessment", assessmentWordId: undefined, tier: "easy",
    context: "", published: Boolean(selectedStory.published), assessmentQuestions: [],
    expected: { vocabulary: "", pinyin: "", translation: "", pos: "" },
  } : null;
  const changeFilter = (setter: (value: string) => void, value: string) => { setter(value); setPage(0); setMessage(""); };
  const download = () => {
    const url = URL.createObjectURL(new Blob([vocabularyEntriesToCsv(filtered)], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `speaking-vocabulary-${lesson || "all"}.csv`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const deleteQuizWord = async (entry: VocabularyEntry) => {
    if (!entry.assessmentWordId || !window.confirm(`Delete quiz vocabulary ${entry.word}? This removes all three rounds.`)) return;
    setActionError(""); setMessage("");
    try {
      const story = await deleteQuizVocabularyWord(entry.storyId, entry.assessmentWordId);
      setStories(current => current.map(item => item.id === story.id ? story : item));
      setMessage(`Deleted quiz vocabulary ${entry.word}.`);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Could not delete quiz vocabulary.");
    }
  };

  return <section className="av-page" aria-label="Speaking vocabulary">
    <div className="av-filters">
      <label className="av-search">Search<div><Icon name="search" size={18} /><input type="search" value={query} onChange={e => changeFilter(setQuery, e.target.value)} placeholder="Chinese, pinyin or meaning" /></div></label>
      <label>Lesson<select value={lesson} onChange={e => { changeFilter(setLesson, e.target.value); setStoryId(""); }}>
        <option value="5-8">Lessons 5-8</option><option value="">All lessons</option>
        {lessons.map(n => <option key={n} value={String(n)}>Lesson {n}</option>)}
        <option value="null">Unassigned</option>
      </select></label>
      <label>Speaking story<select value={storyId} onChange={e => changeFilter(setStoryId, e.target.value)}>
        <option value="">All stories</option>{availableStories.map(story => <option key={story.id} value={story.id}>{story.lessonNumber ? `${story.lessonNumber}-${story.lessonSubOrder ?? 1} ` : ""}{story.title}</option>)}
      </select></label>
      <label>Review<select value={review} onChange={e => changeFilter(setReview, e.target.value)}>
        <option value="">All entries</option><option value="unverified">Book source unverified</option><option value="missing">Missing metadata</option>
      </select></label>
    </div>
    <div className="av-toolbar">
      <p aria-live="polite">{loading ? "Loading vocabulary..." : `${filtered.length} entries / ${uniqueWords} unique words`}</p>
      <div className="av-actions">
        {onOpenMaterials && <button type="button" className="av-button" onClick={onOpenMaterials}><Icon name="library" size={18} />Materials</button>}
        {newQuizEntry && <button type="button" className="av-button" onClick={() => { setActionError(""); setMessage(""); setEditing(newQuizEntry); }}><Icon name="plus" size={18} />Add quiz word</button>}
        <button type="button" className="av-button" onClick={download} disabled={loading || Boolean(error) || !filtered.length}><Icon name="download" size={18} />Export CSV</button>
      </div>
    </div>
    {message && <p className="av-success" role="status">{message}</p>}
    {actionError && <p className="av-error" role="alert">{actionError}</p>}
    {error ? <div className="av-empty" role="alert"><p>{error}</p><button type="button" className="av-button" onClick={() => setReload(n => n + 1)}><Icon name="retry" size={18} />Try again</button></div>
      : loading ? <div className="av-empty" role="status">Loading Speaking stories...</div>
      : !filtered.length ? <div className="av-empty"><Icon name="book" size={32} /><h2>No vocabulary found</h2>
        <button type="button" className="av-button" onClick={() => { setQuery(""); setLesson(""); setStoryId(""); setReview(""); setPage(0); }}>Clear filters</button></div>
      : <>
        <div className="av-table-wrap" tabIndex={0} role="region" aria-label="Vocabulary table">
          <table className="av-table"><thead><tr><th>Word / pinyin</th><th>Meaning</th><th>Speaking</th><th>Book source</th><th><span className="av-sr-only">Actions</span></th></tr></thead>
            <tbody>{visible.map(entry => {
              const source = vocabularyBookSource(entry);
              return <tr key={entry.id}>
                <td><strong lang="zh-Hant">{entry.word}</strong><span>{entry.pinyin || "Missing pinyin"}</span></td>
                <td><span>{entry.translation || "Missing meaning"}</span><small>{entry.pos || "Missing part of speech"}</small></td>
                <td><span lang="zh-Hant">{entry.storyTitle}</span><small>{entry.lessonNumber ? `${entry.lessonNumber}-${entry.lessonSubOrder ?? 1} / ` : ""}{entry.source === "quiz-assessment" ? "Quiz bank" : entry.storyWide ? "Story-wide" : `Scene ${entry.frameIndex + 1}`}</small></td>
                <td>{source ? <><span className="av-source">{source.kind}</span><small>{source.book}, p. {source.page}</small></> : <span className="av-unverified">Not verified</span>}</td>
                <td className="av-row-actions">
                  <button type="button" className="av-icon-button" title={`View quiz questions for ${entry.word}`} aria-label={`View quiz questions for ${entry.word}`} onClick={() => { setPreviewing(entry); setMessage(""); }}><Icon name="eye" size={19} /></button>
                  <button type="button" className="av-icon-button" title={`Edit ${entry.word}`} aria-label={`Edit ${entry.word}, ${entry.source === "quiz-assessment" ? "quiz vocabulary" : entry.storyWide ? "story-wide vocabulary" : `scene ${entry.frameIndex + 1}`}`} onClick={() => { setActionError(""); setEditing(entry); setMessage(""); }}><Icon name="edit" size={19} /></button>
                  {entry.source === "quiz-assessment" && <button type="button" className="av-icon-button av-danger-button" title={`Delete ${entry.word}`} aria-label={`Delete ${entry.word}, quiz vocabulary`} onClick={() => void deleteQuizWord(entry)}><Icon name="trash" size={19} /></button>}
                </td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        <div className="av-pagination">
          <span>{currentPage * PAGE_SIZE + 1}-{Math.min((currentPage + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}</span>
          <div><button className="av-icon-button" type="button" aria-label="Previous page" title="Previous page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><Icon name="chevron-left" /></button>
            <span>Page {currentPage + 1} of {pageCount}</span>
            <button className="av-icon-button" type="button" aria-label="Next page" title="Next page" disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}><Icon name="chevron-right" /></button></div>
        </div>
      </>}
    {editing && <VocabularyEditor key={editing.id} entry={editing} onClose={() => setEditing(null)} onSaved={story => {
      setStories(current => current.map(item => item.id === story.id ? story : item));
      const savedQuizVocabulary = editing.source === "quiz-assessment";
      setEditing(null); setActionError(""); setMessage(savedQuizVocabulary ? (editing.assessmentWordId ? "Quiz vocabulary saved. All three rounds now use the updated data." : "Quiz vocabulary added.") : "Vocabulary saved.");
    }} />}
    {previewing && <QuestionPreview key={previewing.id} entry={previewing} story={stories.find(story => story.id === previewing.storyId)} onClose={() => setPreviewing(null)} />}
  </section>;
}
