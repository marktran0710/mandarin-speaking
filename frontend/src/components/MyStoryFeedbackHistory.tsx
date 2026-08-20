import type { StorySubmission } from "../services/database";
import { BiLabel, BiText } from "./BiLabel";
import StoryFeedbackCard from "./StoryFeedbackCard";

export default function MyStoryFeedbackHistory({
  submissions,
}: {
  submissions: StorySubmission[];
}) {
  if (submissions.length === 0) return null;

  return (
    <section className="my-story-feedback-history" aria-label="My story feedback history">
      <p className="stories-kicker">
        <BiLabel zh="回顧和進步" pinyin="Huígù hé jìnbù" en="Review and improve" />
      </p>
      <h2>
        <BiLabel zh="我的故事回顧" pinyin="Wǒ de gùshì huígù" en="My Story Feedback" />
      </h2>
      <p className="stories-subtitle">
        <BiText
          zh="再看一次你交過的故事，跟著建議練習，下次會更好。"
          pinyin="Zài kàn yí cì nǐ jiāo guò de gùshì, gēnzhe jiànyì liànxí, xiàcì huì gèng hǎo."
          en="Look back at stories you've submitted and follow the suggestions to improve next time."
        />
      </p>
      <div className="my-story-feedback-list">
        {submissions.map((sub) => (
          <details key={sub.id} className="my-story-feedback-item">
            <summary>
              <span className="msfh-title">{sub.storyTitle}</span>
              <span className="msfh-date">
                {new Date(sub.submittedAt).toLocaleDateString()}
              </span>
            </summary>
            <StoryFeedbackCard
              feedback={sub.storyFeedback}
              concatenatedAudioUrl={sub.concatenatedAudioUrl}
              scenes={sub.scenes}
            />
          </details>
        ))}
      </div>
    </section>
  );
}
