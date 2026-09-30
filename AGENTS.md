# Project instructions

## Git workflow: commit every completed task

- Work in the current repository checkout and branch. Do not create Git worktrees.
- Once each task is implemented, verified as appropriate, and its final diff reviewed, commit that task immediately before starting the next task or sending the final response. Do not wait for an additional commit request or combine unrelated completed tasks into one commit.
- Inspect the branch, HEAD, working tree, and staged changes before editing and again before committing so concurrent changes are noticed.
- Stage and commit only the files or hunks belonging to the current task. Preserve unrelated changes made by the user or other agents, including changes already staged.
- If a merge, rebase, cherry-pick, or concurrent commit/edit causes a conflict with the task, warn the user immediately. Identify the affected files, commits when known, and the operation involved; explain what blocks completion. Preserve both sides and do not commit unresolved conflicts or silently overwrite others' work.
- If the task cannot be committed, report the concrete reason and the remaining changes. Do not claim the task is fully complete.
- Include the commit hash and a short summary in the final response.
