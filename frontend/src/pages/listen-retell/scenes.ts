import type { Topic } from "../../components/TopicSelector";

export interface ListenScene {
  image: string;
  script: string;
  audioUrl: string;
  vocabulary: string[];
}

const SAMPLE_SCENES: ListenScene[] = [
  {
    image: "/sample-scenes/market.svg",
    script: "市場裡有很多新鮮水果，老闆熱情地招呼客人，大家一起挑選喜歡的水果。",
    audioUrl: "",
    vocabulary: ["市場", "水果", "老闆", "客人", "挑選"],
  },
];

export function buildSceneOptions(publishedTopics: Topic[]): ListenScene[] {
  const fromTopics = publishedTopics.flatMap((topic) =>
    topic.images
      .map((image, index) => ({
        image,
        script: topic.listenScripts?.[index] || "",
        audioUrl: topic.listenAudioUrls?.[index] || "",
        vocabulary: topic.vocabulary[index] || [],
      }))
      .filter((scene) => scene.script || scene.audioUrl),
  );
  return fromTopics.length > 0 ? fromTopics : SAMPLE_SCENES;
}

export const DEFAULT_LISTEN_SCENE = SAMPLE_SCENES[0];
