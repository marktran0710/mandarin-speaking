# Student flow

```text
Student login
  → Learner Workspace
  → Practice / Progress / Picture talk
  → Select activity
  → Quiz gate
  → Vocabulary quiz (when required)
  → Story overview
  → Speaking activity
  → Recording and analysis
  → Feedback and focused practice
  → Next scene / summary
```

The workspace CTA and the activity-level gate use the same `topicHasQuiz` and
student-scoped completion storage. A learner cannot bypass the first quiz by
using the workspace CTA; completing the quiz changes the CTA to `Start activity`.

