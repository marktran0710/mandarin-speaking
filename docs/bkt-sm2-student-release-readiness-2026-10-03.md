# Đánh giá BKT / SM-2 trước khi release cho student

Ngày đánh giá: **2026-10-03, Asia/Taipei**. Branch `main`, source baseline
`d310feeac885ecbade8352399352a91407aebab3`, schema local `0062`.

## Quyết định

**Chưa nên release rộng rãi ở trạng thái hiện tại.** BKT và modified SM-2 có
nền tảng tính toán và tích hợp backend tốt, nhưng luồng student còn lỗi lưu
evidence đã tái hiện được, và cấu hình model synthetic có thể đi theo database
dev sang production. Sau khi sửa các lỗi P1 và nghiệm thu luồng browser, có thể
mở pilot có giám sát. Hiệu quả dự đoán và ghi nhớ trên học viên thật vẫn cần
đánh giá riêng trong pilot.

Đánh giá này đọc source, chạy regression trên database PostgreSQL tạm mới,
kiểm tra production build và audit database developer trong transaction
`REPEATABLE READ, READ ONLY`. Không thay đổi model, lịch ôn hay dữ liệu student
hiện có. Chưa kiểm tra một deployment production hay chạy nghiệm thu browser
với student thật; không xem các phần đó là đã pass.

## Các phát hiện ảnh hưởng release

### P1 — Lưu từng câu thiếu vocabularyVersion ở bài đã sửa vocabulary

Nguồn: `frontend/src/features/vocabulary/hooks/useQuizSession.ts:302`;
`backend/services/vocab_quiz_attempt_service.py:62`.

Hook nhận `vocabularyVersion` và gửi nó khi lưu completed attempt, nhưng không
gửi trong request `/api/vocab-quiz-responses`. Backend chủ động từ chối request
không có version nếu `vocabulary_version > 1`. Catch ở dòng 316 nuốt lỗi;
student vẫn chuyển sang câu tiếp theo.

Tái hiện bằng hook với version 2: request lưu từng câu không có version, trong
khi request cuối round có version 2. Tái hiện API trên database tạm: cùng một
đáp án của bài version 2 trả **409 và không có ledger row** khi thiếu version;
thêm version 2 trả **200**. Cả **12/12 bài published hiện tại đều ở version 2**,
nên đây là đường chạy hiện hành, không chỉ tình huống giả định.

Nếu student refresh hoặc đóng tab trước khi hoàn tất round, các đáp án đó
không được lưu vào BKT. Nếu final save thành công thì nó có thể lưu lại cả
round; vì vậy lỗi không có nghĩa mọi completed attempt đều mất.

Điều kiện đóng: gửi version cho cả partial/completed save, xử lý stale version
rõ ràng; test bài version 2+, refresh giữa round và vocabulary thay đổi khi
đang làm bài. Không bỏ guard version của backend.

### P1 — UI báo hoàn thành sau khi cả partial và final save thất bại

Nguồn: `frontend/src/features/vocabulary/hooks/useQuizSession.ts:159-212`;
`frontend/src/features/vocabulary/hooks/useQuizSessionData.ts:108`.

`finish()` cộng sao local trước khi server xác nhận. Khi final save thất bại
với lỗi thông thường, hook vẫn lưu local snapshot, gọi `onComplete` và chuyển
sang summary. Tái hiện bằng cách cho cả hai API save reject: hook vẫn có sao 1,
screen `summary`, callback completion chạy và `practiceError` rỗng.

Comment cho rằng local snapshot được POST lại ở lần đọc progression sau,
nhưng `useQuizSessionData` hiện chủ động đọc lịch sử server và **không POST lại
local mirror**. Do đó hiện không có cơ chế phục hồi tự động như comment mô tả.
Server progression vẫn bảo vệ gate sau reload; điều đó không khắc phục việc
student đã được báo hoàn thành khi evidence chưa lưu. Với maintenance, việc
lưu thất bại cũng khiến lịch ôn không cập nhật dù UI đã đi tới kết quả.

Điều kiện đóng: trạng thái lỗi/chưa đồng bộ hiển thị rõ; retry với response ID
ổn định; chỉ coi round đã lưu và cập nhật progression chính thức sau xác nhận
server. Nghiệm thu mất mạng, 409, 5xx, reload và retry không tạo observation
hay SRS event trùng. Đây là một lỗi riêng với việc thiếu version ở trên.

### P1 trước deployment — Model synthetic active vẫn có thể được serve trong production

Nguồn: `backend/analytics/learner_model/bkt/deployment.py:49-70,136-140,175`.

Registry local đang active
`bkt-synthetic-candidate-20260928T012541Z-36b68139`,
`evidence_origin=synthetic`, `promotable=false`. Activation mới bị chặn khi
`APP_ENV=production`, nhưng loader của model **đã active** không kiểm tra
environment, provenance hay promotability. Audit đổi environment của process
sang production rồi gọi loader với cùng registry: vẫn nhận đúng config đó.
Database không bị sửa trong phép thử này.

Vì vậy chỉ đổi APP_ENV hoặc chuyển nguyên database dev không tự loại model
simulation khỏi đường phục vụ. Điều này chưa chứng minh một deployment
production hiện có đang bị ảnh hưởng; deployment đó chưa được truy cập.

Điều kiện đóng: có quy tắc fail-closed hoặc fallback rõ ràng cho synthetic
deployment đã tồn tại; kiểm tra config/registry ngay tại môi trường release.
Model engineering default có thể dùng cho pilot nếu được ghi nhận đúng là
chưa calibrated; không cần giả định phải có human fit mới bắt đầu pilot.

### P2 — Các cổng regression tự động chưa đủ để nghiệm thu release

Nguồn: `.github/workflows/ci.yml:36-59`;
`backend/tests/conftest.py:84,117-123`;
`frontend/e2e/learning-engine-verification.spec.ts:45`;
`frontend/src/features/vocabulary/hooks/useQuizSessionData.ts:169-176`.

Workflow backend gọi `pytest` nhưng không khai báo PostgreSQL service,
TEST_DATABASE_URL hay bước migrate. Conftest bắt buộc URL riêng an toàn và
thoát khi thiếu. Đây là khoảng trống cấu hình nhìn thấy trong workflow,
không phải kết quả của một GitHub Actions run được truy cập trong review này.

Browser spec BKT chờ response `/weak-words`, trong khi hook của student đã
chuyển sang `/review-queue` để lấy cả weak và due. Spec hiện không chứng minh
luồng đang chạy; cần cập nhật theo API thực tế rồi chạy trên fixture riêng.

Điều kiện đóng: CI có database test/migration, và browser acceptance kiểm tra
diagnostic đủ bài → repair đúng dimension → enrollment → due success → lapse
→ repair, cùng refresh/login lại, version mới, save failure và retry.

## Những gì đang vận hành đúng

| Lớp | Kết quả đã kiểm tra | Giới hạn |
| --- | --- | --- |
| BKT core | Bayes observation update rồi learning transition; guess/slip riêng cho MCQ và typed; golden vectors pass. | Pass phép tính không chứng minh tham số phù hợp học viên thật. |
| Chấm đáp án | Resolver dựa vào published assessment; item không hợp lệ không tạo BKT evidence và correctness client không quyết định evidence chính thức. | UI vẫn có thể tính kết quả local; lỗi đồng bộ cần sửa như P1. |
| Diagnostic | Ba round cần covering toàn bộ từ của bài trong completed run; partial/duplicate không unlock. | Dữ liệu SIM hiện chưa thỏa gate này. |
| Corrective practice | Mọi dimension sai cần hai correct corrective answers liên tiếp cùng dimension; sai lại mở lại yêu cầu. | Lặp lại item cũ có thể phản ánh nhớ đáp án, chưa chứng minh transfer. |
| STRONG | Diagnostic hoàn tất, đủ ba dimension, số observation tối thiểu, hết unresolved và P(Learned) ≥ 0.95. | Là nhãn của hệ thống, không phải xác suất 95% trả lời đúng. |
| Persistence | Learner transaction lock, stable response slot/fingerprint, conflict handling, replay cache. | Chưa đo tải đồng thời thực tế hay phục hồi backup. |
| Enrollment | Chỉ official STRONG được enroll; không overwrite schedule hiện có bằng corrective practice. | Chưa có operational maintenance evidence trong database local. |
| Modified SM-2 | q=4/2, interval 1 → 6 → 15, failure reset reps=0/interval=1/ease=2.18; due-cycle và retry guards pass. | Đây là scheduling policy chưa có delayed-retention measurement. |
| Lapse/repair | Due failure giảm BKT và mở repair; practice sửa lỗi không trì hoãn due date cũ. | Chưa nghiệm thu cùng luồng trên browser student thật. |
| Queue/UI selection | Due chỉ cho official STRONG, weak không bị đưa vào maintenance; ưu tiên server và dimension rotation đã có regression. | Browser spec cần cập nhật endpoint. |
| Production clock | Production bỏ today override và dùng ngày 24 giờ, không dùng compression dev. | Local đang là development; phải kiểm tra environment release riêng. |

SM-2 hiện là bản sửa đổi: binary grade và `round` interval khác thang 0–5 và
upward rounding trong [mô tả gốc của Woźniak](https://www.super-memory.org/archive/english/ol/sm2.htm).
Với q=4, ease không tăng; sau lapse nó giảm và không phục hồi qua các success
binary. Đây là tradeoff đã được ghi nhãn trong code, không phải phát hiện sai
phép tính. Theo dõi tần suất ôn và retention trong pilot trước khi đổi policy.

BKT hiện không có time-dependent forgetting, pooled một latent state cho
meaning/pinyin/context và learning transition chung cho các activity. Dimension
repair bổ sung guard cho progression nhưng không biến mô hình thành ba skill
độc lập. [Implementation và variants của pyBKT](https://github.com/CAHLR/pyBKT)
là đối chiếu tham khảo; tính hợp lệ của các giả định ở ứng dụng này cần dữ liệu.

## Dữ liệu vận hành hiện tại: audit mới, read-only

- Ledger: **4.670** rows, không có duplicate `(student_id, quiz_id, attempt_order)`;
  không thiếu UTC timestamp, response fingerprint, activity hay dimension trong
  các field được audit.
- **1.164/1.164** mastery rows thuộc 41 student identities khớp full-ledger replay
  với config active, placement initialization, observation/outcome counts và
  parameter fingerprint; không thiếu/thừa cache row trong scope kiểm tra.
- Published bank: **12/12** bài pass production shape validator; **218** word/lesson
  pairs, **654** items, đủ meaning/pinyin/context. Đây là kiểm tra contract,
  không phải đánh giá distractor quality hay ambiguity bởi chuyên gia.
- **40/40** tài khoản SIM được đánh dấu test account. Chúng có **4.480** responses,
  toàn diagnostic; **480/480** observed student/lesson pairs có 0 completed round
  theo full-lesson contract hiện tại; **0** schedule của SIM.
- Toàn database có **3** SRS schedules và **3** events, đều enrollment;
  **0** scheduled-maintenance response/success/failure. Chưa có bằng chứng
  vận hành delayed review hoặc delayed retention.
- Có **176** real-labelled responses thuộc một identity: 120 diagnostic, 56
  personalized practice. Label real không tự chứng minh người thật đã tạo
  answers. Các 40 SIM là dữ liệu synthetic, không được gọi là human pilot.
- Active fit từ 4.480 synthetic responses / 40 accounts / 28 concepts. Stored
  AUC 0.7213, Brier 0.2091, log loss 0.6046 và calibration error 0.0193 là metrics
  lịch sử của simulation, không phải human validation được recompute hôm nay.
- Config active: prior 0.261835, learn 0.131310, MCQ G/S 0.257520/0.089203,
  typed G/S 0.045928/0.152189; mastery cutoff 0.95/minimum observations 3.
  Tại cutoff, next-answer correctness khoảng **87,8% MCQ / 80,8% typed**.
  Không diễn giải P(Learned)=0.95 thành 95% recall ở mọi dạng câu hỏi.
- Local APP_ENV=development, scheduling day 86.400 giây; schema 0062.

## Verification thực hiện hôm nay

- Runner BKT: **112 tests pass**, 7 golden scenarios pass, report không FAIL/BLOCKED.
- Runner SM-2: **63 tests pass**, interval/reset checks pass, report không FAIL/BLOCKED.
  Hai runner có test trùng nhau; không cộng thành tổng distinct.
- Regression backend mở rộng: **291 tests pass trong 33 files** trên database
  tạm, gồm **290 regression hiện có + 1 API reproduction** cho lỗi thiếu
  vocabularyVersion. Reproduction pass nghĩa là hành vi lỗi đã tái hiện được,
  không phải lỗi đã sửa. Các runner có overlap nên không cộng tổng lượt chạy.
- Toàn frontend: **128 files pass, 735 tests pass, 7 skipped**.
- Hai hook reproductions cho P1: **2 pass** theo assertion tái hiện hành vi lỗi;
  đây không phải acceptance pass cho release.
- `npm run build`: TypeScript application check và Vite production build pass.
- Alembic upgrade head chạy thành công trên database tạm của mỗi runner;
  database tạm được drop sau kiểm tra. Không truncate database developer.
- Không chạy voice validation, browser live acceptance, production deployment
  smoke, load test hoặc restore drill trong phạm vi BKT/SM-2 review này.

Raw run artifacts ở thư mục ignored `backend/verification_reports/`, gồm
`student-release-local-audit-20261003.json`,
`student-release-regressions-20261003.json`,
`learning-engine-bkt-20261003T092922Z.{md,json}` và
`learning-engine-sm2-20261003T093119Z.{md,json}`. Hook/API reproduction files
tạm được xóa sau khi kiểm tra; report này là deliverable được commit.

## Thứ tự để mở cho student

1. Sửa hai lỗi persistence P1, thêm regression đúng hợp đồng client/backend
   và nghiệm thu refresh giữa round trên published vocabulary version 2+.
2. Chốt serving provenance ở production, giữ simulation riêng; sửa CI và
   browser spec rồi chạy toàn bộ diagnostic/repair/maintenance/lapse loop.
3. Mở pilot có giám sát: đo lỗi save, duplicate transitions, due backlog,
   repair stuck, thời gian học và lỗi item. Có rollback model/config rõ ràng.
4. Thu human delayed responses và fresh-item probes theo dimension/time gap;
   đánh giá prediction trước update, learner-grouped holdout, calibration,
   baseline và uncertainty. Chỉ kết luận BKT/SM-2 cải thiện học hay đạt mục tiêu
   retention khi có bằng chứng này. Không lấy metrics synthetic thay thế.
