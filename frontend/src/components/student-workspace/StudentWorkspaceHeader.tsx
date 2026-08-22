import StudentIcon from "../StudentIcon";
import { BiText } from "../BiLabel";

interface StudentWorkspaceHeaderProps {
  username: string;
}

export default function StudentWorkspaceHeader({ username }: StudentWorkspaceHeaderProps) {
  return (
    <header className="student-workspace-header student-workspace-header-v2">
      <div className="student-workspace-header-copy">
        <div className="student-workspace-heading">
          <h1>
            <span lang="zh-Hant">我的學習</span>
          </h1>
          <span className="student-workspace-pinyin">Wǒ de xuéxí</span>
        </div>
        <p className="student-workspace-intro">
          <BiText
            zh="選一個方向，慢慢練習。"
            pinyin="Xuǎn yí ge fāngxiàng, mànmàn liànxí."
            en="Choose a path and keep learning, little by little."
          />
        </p>
      </div>
      <div className="student-workspace-header-side">
        <div
          className="student-workspace-identity"
          aria-label={`Student username: ${username}`}
        >
          <span className="student-workspace-identity-avatar" aria-hidden="true">
            <StudentIcon name="user" size={19} />
          </span>
          <span className="student-workspace-identity-copy">
            <span className="student-workspace-identity-label">
              <span lang="zh-Hant">學生帳號</span>
              <span aria-hidden="true"> · </span>
              <span>USERNAME</span>
            </span>
            <strong className="student-workspace-identity-name">{username}</strong>
          </span>
        </div>
        <div className="student-workspace-mark" aria-hidden="true">
          <span>慢</span>
          <span>慢</span>
        </div>
      </div>
    </header>
  );
}
