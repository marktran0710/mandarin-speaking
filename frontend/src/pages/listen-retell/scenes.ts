import type { Topic } from "../../components/TopicSelector";

export interface ListenScene {
  image: string;
  script: string;
  audioUrl: string;
  vocabulary: string[];
}

const SAMPLE_SCENES: ListenScene[] = [
  {
    image: "/sample-scenes/park.svg",
    script: "公園裡下雨了，小朋友們撐著雨傘跑來跑去，找地方躲雨，玩得很開心。",
    audioUrl: "",
    vocabulary: ["公園", "下雨", "雨傘", "跑步", "孩子"],
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
