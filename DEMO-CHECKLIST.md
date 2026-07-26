# DEMO-CHECKLIST — demo real user (tuần 27/07/2026)

> Plan verify trước demo. Claude cập nhật ô tick khi verify xong từng mục;
> bug ghi vào sổ cuối file theo mức 🔴🟡⚪. Hai mục đánh `[NGƯỜI]` là mục
> chỉ người thật làm được (mic/loa thật).
>
> Môi trường demo: **laptop của Hậu, localhost** — FE Vite + backend FastAPI :8000.
> Hình thức: **demo dẫn trước, sau đó user cầm máy tự thử.**

---

## Phase 0 — Kịch bản demo (xương sống của mọi verify)

**Quyết định cần chốt:**
- [x] Story demo chính: **Lesson 5 →「捷運站在哪裡？」(6 部分, 24 詞)** — đã dùng cho toàn bộ verify Phase 1
- [ ] Ngày demo chính xác: `_________`

> Audio test: `demo-verify-audio/` (TTS Hanhan zh-TW) — câu đúng / sai nghĩa / nửa câu + 5 file từ đơn.
> Profile verify: student "Demo Verify 2307" (đã có ⭐⭐ story demo).

**Kịch bản A — phần dẫn (Hậu điều khiển, ~10-12 phút):**

1. Mở app student (`index.html` dev server) — màn `home` → `student-login`
2. Login profile student (⚠️ từ 23/07 chiều: chọn tên từ roster + **mật khẩu, default 123456** — 7896029; tài khoản **admin** mở sẵn mọi gate f60af98, tiện làm backup khi demo kẹt gate) → về shell student, journey bubble hiện trạng thái sao
3. Mở **student-stories** — mục lục Book 1: chỉ vào lesson mở/khóa, 其他 cuối danh sách
4. Chọn story demo → làm **quiz tier 1** (20 câu, đạt ≥14 → ⭐)
5. Làm **quiz tier 2** (22 câu, đạt ≥18 → ⭐⭐) → gate practice mở
6. Vào **practice**: Study step (vocab + phrases + ảnh scene) → Speaking
7. Thu âm câu mẫu bằng mic thật → analyzing → **results flow mới**:
   - Step 結果: verdict + playback + transcript + stats + 發音回饋
   - Bấm CTA → step 練習: focus 1 từ, drill tại chỗ, chip ✓, auto-advance
   - Re-record cả câu → pass → Next scene
8. Đi hết các scene → **View summary**
9. Chuyển sang **teacher app** (`teacher.html`) → login teacher
10. TeacherShell: Overview → Submissions → Star board/Analytics (khớp data student vừa tạo)
11. (Tùy thời gian) Materials / tạo ảnh story

**Kịch bản B — phần user cầm máy (~10 phút, có người kèm):**
- User tự chọn story (có thể đụng lesson khóa), tự làm quiz (có thể rớt),
  tự thu âm (có thể sai nghĩa/thiếu từ → nhánh 改句子), có thể bấm back/refresh.

---

## Phase 1 — Verify xương sống (backend thật) — ngày 1-2

- [x] 1.1 FE + backend cùng chạy; console không error của app — ✓ 23/07 (2 lỗi console là của Chrome extension)
- [x] 1.2 Login student profile OK (tạo mới qua「+ 其他人」); journey bubble hiện 0/2 做測驗 pulse đúng — ✓ 23/07
- [x] 1.3 Mục lục Book 1: Lesson 5 mở, Lesson 6/7 khóa 先完成第5課 đúng — ✓ 23/07 (⚠️ nhóm 其他 không xuất hiện — chưa rõ do không có story unassigned hay bug, xem bug #2)
- [x] 1.4 Quiz tier 1: đủ 20 câu (nghĩa xuôi/ngược + pinyin), mỗi câu 1 đáp án đúng; 20/20 → ⭐ hiện ngay — ✓ 23/07
- [x] 1.4b **Audit quiz toàn diện** (23/07 chiều): test vĩnh viễn `StoryVocabQuiz.audit.test.tsx` sinh ~7.5k câu từ vocab thật cả 7 story × 3 tier, check invariant 1-đáp-án-đúng; + lượt duyệt ngữ nghĩa toàn bộ 397 entry. Tìm & fix 3 bug 🔴 + 146 distractor 🟡 (sổ bug #8-11). Fixture refresh: `Invoke-WebRequest http://127.0.0.1:8000/api/custom-stories -OutFile src/components/__fixtures__/custom-stories.json`
- [x] 1.5 Quiz tier 2: 22 câu (thêm dạng nghe + tone-mark); 22/22 → ⭐⭐; gate Speaking mở đúng lúc, có nút 繼續練習 — ✓ 23/07
- [x] 1.6 Study step: bảng生詞 theo scene + 練習短語 + ảnh đúng story — ✓ 23/07
- [x] 1.7 Speaking: upload audio → transcribe → Praat → feedback, không kẹt (~10s/câu trên máy này) — ✓ 23/07
- [x] 1.8 Results ①結果: verdict đúng nhánh (🎯 pronounce / 📝 vocab đã thấy cả hai); playback + transcript + stats (4/9 個字 · 生詞 6/6) + chips từ fail + 發音回饋 grid + CTA đổi theo verdict — ✓ 23/07
- [x] 1.9 Results ③練習: focus 1 từ, drill tự mở; chip bấm nhảy từ ✓; drill pass (知道) → chip ✓ + footer 5→4 + auto-advance ✓; stepper quay lại ①結果 tự do, step chưa mở bị disable — ✓ 23/07
- [x] 1.8b Results ②改句子 (nhánh vocab): chips 試著加入 + 提示 hint + CTA 再錄一次/練習生詞 — ✓ 23/07
- [ ] 1.10 Luyện xong HẾT từ → banner 🎉 → re-record → mastery pass → Next scene mở — `[NGƯỜI]` TTS không pass nổi tone 2/3 (哪裡, 捷運站…), cần giọng thật đọc chuẩn để đi hết vòng này
- [ ] 1.11 Đi hết 6 scene → View summary — `[NGƯỜI]` phụ thuộc 1.10
- [x] 1.12 Screenshot light mode các màn đã đi — ✓ lưu trong phiên verify 23/07
- [ ] 1.13 `[NGƯỜI]` Mic laptop thu rõ ở khoảng cách ngồi demo; loa phát playback đủ nghe
- [ ] 1.14 `[NGƯỜI]` Độ trễ analyzing trên máy demo chấp nhận được (<~15s/câu)

## Phase 2 — Vùng user tự do — ngày 2-3

- [x] 2.1 Quiz rớt (3/20 trên 士林夜市): màn kết quả tử tế "再答對 11 題就拿到⭐", list từ sai, nút Try again + Practice missed words, không crash, không mất gì — ✓ 23/07
- [x] 2.2/2.3 Thu câu sai nội dung (我喜歡吃蘋果…): story mode này chấm theo **vocab** (verdict 📝, 還缺 6 個詞) chứ không phải 🧭 meaning — meaning-fail chỉ dành cho listen_retell mode. Step 改句子 hiện đúng chips + hint; step 練習 vẫn có (vì có từ fail) — ✓ 23/07. `[NGƯỜI]` test 🧭 trên story listen-retell nếu demo có
- [x] 2.4 Upload audio thay mic: **wav** đi qua pipeline OK (nhiều lần) — ✓ 23/07; webm/mp3 chưa thử riêng
- [x] 2.5 Stepper: quay lại step đã qua OK, step chưa mở disabled — ✓ 23/07
- [x] 2.6 Refresh giữa session: về mục lục, vẫn đăng nhập, không trắng màn (mất vị trí đang đứng trong story — chấp nhận được). ⚠️ Ghi chú: mở teacher.html cùng tab rồi quay lại student = mất session student, phải login lại — trong demo đừng chuyển role trong cùng tab, mở 2 tab riêng — ✓ 23/07
- [x] 2.7 Bấm lesson khóa: không phản ứng, không crash (card đã ghi 先完成第5課) — ✓ 23/07
- [ ] 2.8 Tắt backend, thu âm 1 lần: hiện lỗi thân thiện — `[NGƯỜI]` (backend :8000 đang chạy là instance của bạn, mình không tự tắt; thử lúc rảnh: tắt uvicorn → bấm record → xem thông báo)
- [ ] 2.9 Mobile viewport 390px: `[NGƯỜI]`/Playwright — resize window qua tool bị kẹt maximized; practice pages từng verify mobile (aa9e517), còn TOC/quiz/results chưa
- [ ] 2.11 `[NGƯỜI]` Rà alignment student-side bằng mắt (TOC/drill-in/session/quiz/speaking, light+dark) — bị chặn bởi login mật khẩu mới (Claude không tự điền mật khẩu); teacher-side + Home/login đã rà xong 23/07, quét tĩnh student CSS không thấy pattern lỗi
- [x] 2.10 Tone practice + My Stories workbook: mở không lỗi, dữ liệu đúng — ✓ 23/07

## Phase 3 — Teacher mode — ngày 3-4

- [x] 3.1 Login teacher (chỉ cần tên, không password) → Overview: stats 200 recordings/75 fluency/64% tone, submissions + help queue hiện raise-hand đang chờ — ✓ 23/07
- [x] 3.2 Submissions: **crash lúc đầu (bug #5, đã fix)** → giờ render 12 bài đầy đủ scene cards + chips + audio + 整個故事回顧; 2 bản upload verify hiện ngay — ✓ 23/07
- [x] 3.3 Recordings & Help: tab Recordings 200 + Help requests 1; recording kèm transcript/tone/Praat đúng — ✓ 23/07. `[NGƯỜI]` nút "Mark helped" chưa bấm (sẽ đổi dữ liệu queue thật của hau test 07/20)
- [x] 3.4 Materials: Story Builder + AI Image Builder tab; Teacher Story Library 7 story, Unpublish/Edit/Import — ✓ 23/07 (chưa test tạo story mới end-to-end)
- [x] 3.5 Students (Progress/Roster) + Analytics (Quiz 86 · Recordings 200 · Insights): số liệu khớp hoạt động verify — ✓ 23/07. ⚠️ Students/Progress layout lệch (bug #6)
- [x] 3.6 Dark mode 6/6 view: không chữ chìm, token màu đúng — ✓ 23/07
- [x] 3.7 Light mode 6/6 view: screenshot lưu trong phiên verify — ✓ 23/07
- [x] 3.8 Toggle dark/light qua lại: state không vỡ — ✓ 23/07 (đã trả về Light)

## Cross-cutting — chạy suốt tuần

- [x] X.1 `tsc --noEmit` sạch (trừ vite.config pre-existing) — ✓ 23/07
- [x] X.2 `vitest run`: đúng baseline 13 fail pre-existing, KHÔNG tăng — ✓ 23/07 (13 fail / 186 pass)
- [x] X.3 `vite build` production thành công — ✓ 23/07 (1.63s; cảnh báo chunk >500kB, ghi ⚪)
- [ ] X.4 Console không error mới trên mọi màn đã đi qua
- [ ] X.5 Các trang đi qua thẳng hàng theo `--content-max: 1160px`

## Phase 4 — Fix bug + re-verify — ngày 4-5

- [ ] Toàn bộ 🔴 đã fix + re-verify mục liên quan
- [ ] 🟡 còn lại đã ghi chú "né" vào kịch bản
- [ ] Không sửa code vùng ⚪ (tránh regression sát ngày)

## Phase 5 — Dress rehearsal (1 ngày trước demo)

- [ ] Chạy nguyên kịch bản A đầu-cuối không dừng, bấm giờ
- [ ] Chạy thử 3-4 hành vi "user tự do" tiêu biểu của kịch bản B
- [ ] Reset dữ liệu demo về trạng thái sạch (sao, attempts, recordings) — script/ghi chú cách reset: `_________`
- [ ] Sạc + tắt notification máy demo; backup: quay video màn hình 1 lượt demo hoàn chỉnh phòng khi hỏng giữa buổi

---

## Sổ bug

> 🔴 blocker (fix ngay) · 🟡 demo-visible (fix nếu kịp, không thì né trong kịch bản) · ⚪ ngoài kịch bản (sau demo)

| # | Mức | Màn/bước | Mô tả | Trạng thái |
|---|-----|----------|-------|------------|
| 1 | ⚪ | build | Chunk index.js 631kB >500kB — cân nhắc code-split sau demo | Ghi nhận |
| 2 | 🟡 | Mục lục Book 1 | Nhóm 其他 không hiện trong TOC — xác nhận có phải mọi story đều đã gán lesson không; nếu có story unassigned mà không hiện là bug | Cần check |
| 3 | 🟡 | Drill 練習 | Khi shape pass nhưng content_match=false (在): card hiện "非常好 ✓過關 Passed" nhưng chip vẫn ✗ — 2 tín hiệu mâu thuẫn, student dễ hỏi "sao pass rồi mà chưa ✓?". Đề xuất: content_match=false thì đổi chip verdict thành "再試一次" thay vì ✓過關 | Cần sửa/né |
| 4 | ⚪ | Screenshot CDP | Renderer hay treo screenshot ~30s sau click (animation?) — chỉ ảnh hưởng tool tự động, không ảnh hưởng student | Ghi nhận |
| 5 | 🔴 | Teacher Submissions | Crash trắng màn "Cannot read properties of undefined (reading 'judged')" — submission cũ thiếu dimension trong StoryFeedback (schema drift) | **ĐÃ FIX 23/07** — guard `dimension?` trong StoryFeedbackCard.tsx DimensionRow; re-verify trên app thật ✓ |
| 3b | 🟡 | Drill 練習 | (fix cho #3) WordPracticeDrill: shape pass + content_match=false giờ hiện "✗ 再試一次" thay vì "✓過關" | **ĐÃ FIX 23/07** — tsc+test pass; case khó ép backend tái hiện, re-verify khi gặp lại trong dress rehearsal |
| 6 | 🟡 | Teacher Students/Progress | Layout lệch: panel legacy mang `margin:auto` bị flex column của shell bóp shrink-to-content | **ĐÃ FIX 23/07** — `.tdash-workspace .teacher-panel { width:100% }` trong TeacherDashboardPage.css; re-verify ✓ |
| 2✓ | — | Mục lục Book 1 | ĐÓNG — không phải bug: cả 7 story đều đã gán lesson (5/6/7), không có story unassigned nên 其他 đúng ra là không hiện | Đóng 23/07 |
| 7 | ⚪ | Nội dung story | Story tên "我的錢包在哪裡?" đang gán **Lesson 7**, nhưng 我的錢包在哪裡 lại là *tiêu đề Lesson 5* trong mục lục Book 1 — user mở khóa L7 sẽ thấy lạ. Xem lại gán lesson của story này | Cần review nội dung |
| 8 | 🔴 | Quiz data | Cột translation lệch index ở 4 scene (他們="afterwards", 去="to want"…) — đáp án quiz SAI, "they" bị chấm sai | **ĐÃ FIX 23/07** — realign 3 story qua API (`scripts/fix-quiz-data.mjs`), backup tại `demo-verify-audio/custom-stories-backup-2026-07-23.json` |
| 9 | 🔴 | Quiz code | `storyToTopic` gắn mảng AI (distractor/cloze/synonym/lookalike) của cột easy vào tier medium/hard có danh sách từ riêng → synonym question chấm "今天≈名字" là đúng | **ĐÃ FIX 23/07** — gate `tierUsesEasyVocabulary` trong teacherStories.ts |
| 10 | 🔴 | Quiz code | Câu cloze lộ đáp án khi từ xuất hiện 2 lần trong câu ("____啊！他們**有**…") | **ĐÃ FIX 23/07** — collectQuizEntries chỉ nhận candidate chứa từ đúng 1 lần |
| 11 | 🟡 | Quiz data | 146 distractor tiếng Anh đồng nghĩa với đáp án (好吃→"tasty", 我→"me", 兩點半→"half past two"…) = 2 đáp án đúng ở tier 2+ | **ĐÃ FIX 23/07** — gỡ qua `scripts/fix-quiz-distractors.mjs`; story MỚI sau này cần chạy lại lượt duyệt ngữ nghĩa |
| 12 | 🟡 | Teacher Overview | Hàng stat card lệch phải ~95px so với header/panel (margin:auto trong flex column của shell) | **ĐÃ FIX 23/07** — mở rộng rule width:100% cho nhóm class legacy (TeacherDashboardPage.css) |
| 13 | 🟡 | Teacher Analytics | Hàng stat tile dừng lửng (grid cứng `repeat(4,1fr)` với 3 tile) | **ĐÃ FIX 23/07** — `repeat(auto-fit, minmax(220px,1fr))` |
| 14 | 🔴 | Teacher Insights | Cả tab trắng: backend `VALID_MODES` không nhận mode tier1/2/3 → 400; kèm panel shrink-centered | **ĐÃ FIX 23/07** — thêm tier modes vào `vocab_quiz_analytics.py` + `.insights-view` vào rule width; Insights render đủ (Star Board/IRT/Hardest Words), verify cả light lẫn dark; backend 416 test pass |
| 15 | ⚪ | Teacher Insights | Class Star Board hiện raw id `custom-story-178…` thay vì tên story | Sau demo |
| 16 | 🟡 | Teacher Analytics | Chart "Accuracy by quiz mode" chỉ vẽ mode cũ (Speed/Strikes/Free), chưa có cột tier1/2/3 — cùng họ #14 nhưng phía frontend chart | Cần fix hoặc né khi demo |
| 17 | ⚪ | Alignment sweep | Quét tĩnh toàn bộ: các `margin:auto` còn lại đều trong block context (hợp lệ); Roster hẹp 560px là chủ đích; padding lẻ 11-15px là nội bộ input, không đụng | Đóng 23/07 |
