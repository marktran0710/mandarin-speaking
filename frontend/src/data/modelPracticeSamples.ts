export interface ModelPracticeSample {
  sentence: string;
  pinyin: string;
  meaning: string;
  audioUrl: string;
}

const sampleAudioUrl = (filename: string) =>
  `/uploads/examples/${filename}`;

/**
 * Committed, offline-safe model recordings used when a teacher-authored
 * scene has not received its own model voice yet. The transcript for each
 * clip was checked against the bundled local Mandarin Whisper model.
 */
export const MODEL_PRACTICE_SAMPLES: ModelPracticeSample[] = [
  {
    sentence: "姐姐在家裡做飯。",
    pinyin: "Jiějie zài jiālǐ zuòfàn.",
    meaning: "Older sister is cooking at home.",
    audioUrl: sampleAudioUrl("pic1_example.mp3"),
  },
  {
    sentence: "中午的時候，弟弟和同學一起去外面的麵店吃午餐。",
    pinyin: "Zhōngwǔ de shíhou, dìdi hé tóngxué yìqǐ qù wàimiàn de miàndiàn chī wǔcān.",
    meaning: "At noon, the younger brother and his classmate go to a noodle shop for lunch.",
    audioUrl: sampleAudioUrl("pic2_example.mp3"),
  },
  {
    sentence: "吃飽以後，他們回到大樓裡上中文課，學中文。",
    pinyin: "Chī bǎo yǐhòu, tāmen huí dào dàlóu lǐ shàng Zhōngwén kè, xué Zhōngwén.",
    meaning: "After eating, they return to the building for Chinese class.",
    audioUrl: sampleAudioUrl("pic3_example.mp3"),
  },
  {
    sentence: "下課以後，風景很好，他們在校園裡高興地照相。",
    pinyin: "Xiàkè yǐhòu, fēngjǐng hěn hǎo, tāmen zài xiàoyuán lǐ gāoxìng de zhàoxiàng.",
    meaning: "After class, the scenery is beautiful, and they happily take photos on campus.",
    audioUrl: sampleAudioUrl("pic4_example.mp3"),
  },
];

export function modelPracticeSampleFor(sceneIndex: number): ModelPracticeSample {
  const safeIndex = Number.isFinite(sceneIndex) ? Math.max(0, Math.floor(sceneIndex)) : 0;
  return MODEL_PRACTICE_SAMPLES[safeIndex % MODEL_PRACTICE_SAMPLES.length];
}
