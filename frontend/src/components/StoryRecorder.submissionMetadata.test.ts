import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const runtimeSource = readFileSync(
  resolve(process.cwd(), "src/components/StoryRecorderRuntime.js"),
  "utf8",
);

describe("StoryRecorder submission progression metadata", () => {
  it("submits the canonical story and level identity before marking the level complete", () => {
    expect(runtimeSource).toContain(
      'storyId:t.id,baseStoryId:t.sourceStory?.id??t.id,difficultyLevel:t.difficultyLevel??"easy",storyTitle:t.name',
    );
    expect(runtimeSource).toContain(
      'gn(!0),dt(null),t.sourceStory&&t.difficultyLevel&&pr(t.sourceStory.id,t.difficultyLevel)',
    );
    expect(runtimeSource).toContain(
      'ge={baseStoryId:t.sourceStory?.id??t.id,difficultyLevel:t.difficultyLevel??"easy",sceneIndex:r',
    );
    expect(runtimeSource).toContain(
      'function Er(t,e){if(t.imageIndex===void 0)return null;const u=t.praatMetrics,r=u?.ai_feedback?.vocabulary_coverage;return{baseStoryId:t.baseStoryId??e?.sourceStory?.id??e?.id,difficultyLevel:t.difficultyLevel??e?.difficultyLevel??"easy"',
    );
    expect(runtimeSource).toContain('F=Er(f,t);');
    expect(runtimeSource).toContain(
      'Object.values(M).sort((s,a)=>s.sceneIndex-a.sceneIndex).map(s=>({...s,baseStoryId:t.sourceStory?.id??t.id,difficultyLevel:t.difficultyLevel??"easy"}))',
    );
  });

  it("does not mark a level complete from an incomplete recording gate", () => {
    expect(runtimeSource).toContain(
      '_t=qe>0&&W.every(e=>!!M[e]&&(k||(B[e]??!1)&&(q[e]??!1)))',
    );
  });
});
