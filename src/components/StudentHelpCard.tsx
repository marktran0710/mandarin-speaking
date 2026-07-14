import { useState } from "react";
import type { HelpRequest } from "../services/database";
import { BiLabel, BiText } from "./BiLabel";
import { getSessionName } from "../utils/myStoriesUtils";

export default function StudentHelpCard({
  helpRequests,
  onRaiseHand,
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}) {
  const [message, setMessage] = useState("我的故事需要幫忙。 I need help with my story.");
  const studentName = getSessionName("studentSession", "Student");
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-card" aria-label="Ask teacher for help">
      <div>
        <p className="stories-kicker">
          <BiLabel zh="老師幫忙" pinyin="Lǎoshī bāngmáng" en="Teacher support" />
        </p>
        <h2>
          {activeRequest ? (
            <BiLabel zh="已舉手" pinyin="Yǐ jǔshǒu" en="Your hand is raised" />
          ) : (
            <BiLabel zh="舉手問問題" pinyin="Jǔshǒu wèn wèntí" en="Raise your hand" />
          )}
        </h2>
        <p>
          {activeRequest ? (
            <BiText
              zh="老師已經看到你舉手了。如果問題不一樣了，可以再說一次。"
              pinyin="Lǎoshī yǐjīng kàndào nǐ jǔshǒu le. Rúguǒ wèntí bù yíyàng le, kěyǐ zài shuō yí cì."
              en="Your teacher can see your request. You can update the note if your question changed."
            />
          ) : (
            <BiText
              zh="一邊做故事，一邊可以偷偷舉手，老師會看到。"
              pinyin="Yìbiān zuò gùshì, yìbiān kěyǐ tōutōu jǔshǒu, lǎoshī huì kàndào."
              en="Send a quiet help request while you keep working on your story."
            />
          )}
        </p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onRaiseHand?.(message);
        }}
      >
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          aria-label="Help request message"
          placeholder="老師可以幫你什麼？ What should the teacher help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? (
            <BiLabel zh="再舉手一次" pinyin="Zài jǔshǒu yí cì" en="Update request" />
          ) : (
            <BiLabel zh="舉手" pinyin="Jǔshǒu" en="Raise hand" />
          )}
        </button>
      </form>
    </section>
  );
}
