# Launch-day checklist — Reel 🎬

> Treat this as the single source of truth for launch day. Tick boxes as you go. All times are **PT**; convert as needed.

---

## T-72h (Saturday) — pre-launch hardening

- [ ] Final pass on README: typos, broken links, install instructions resolve.
- [ ] Confirm `uv sync && make check` passes on a fresh clone (don't trust your dev machine).
- [ ] Publish to PyPI as a release candidate (e.g. `0.1.0rc1`) and install in a clean venv: `uv pip install reel-vcr==0.1.0rc1 && reel --help`.
- [ ] Tag the release commit (`v0.1.0`) but **do not push the tag yet** — push happens on launch morning so the timestamp matches the post.
- [ ] Record the 60-second demo GIF (Sprint 2.9 — deferred but want it for launch). Embed it in README + landing page.
- [ ] **Create GitHub issue templates** (`.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `question.yml`). Traffic will arrive within minutes of the HN post — bare-text issues are noisy and you won't have time to sort them on the day.
- [ ] Add a `discussions` tab and seed it with 3 starter threads: "what should we adapter-add next?", "show your cassette workflow", "feedback wanted: pytest ergonomics".
- [ ] Set up `CODEOWNERS` so issue notifications route to your inbox correctly.

## T-48h (Sunday) — content freeze

- [ ] All 9 marketing files reviewed and copy-edited.
- [ ] `<REPO_URL>` and `<DOCS_URL>` placeholders replaced with real URLs in every launch file.
- [ ] Twitter thread loaded into your scheduler of choice (Typefully / Buffer / native X scheduling). Schedule for **9:05am PT Tuesday** — five minutes after the HN post lands.
- [ ] Bluesky thread loaded similarly.
- [ ] r/Python, r/MachineLearning, r/LocalLLaMA posts saved as drafts in each subreddit's compose UI so you only need to hit submit.
- [ ] Outreach DMs from `maintainer-outreach.md` queued in your DM tool of choice. **Do not send yet** — they go out after the HN post lands so the link is fresh.
- [ ] Outreach newsletter list (`outreach.csv`) reviewed. P1 contacts will be DM'd / emailed on launch morning; P2 in the afternoon; P3 the day after.

## T-24h (Monday evening) — last-mile

- [ ] Sleep early. Set alarm for **7:30am PT Tuesday**.
- [ ] Stash the HN body text in a local file you can copy-paste from without re-formatting. HN strips markdown — body is plain text with manual line breaks.
- [ ] Verify the project's CI badge is green on `main`. A red badge on the README on launch day is the worst-case bug report.
- [ ] Run `reel doctor` on three different machines (macOS, Linux, WSL) to confirm install works. Note any extras-install gotchas to keep ready in a "Common install issues" thread.

---

## Launch day — Tuesday

### 7:30am PT — wake up, coffee, no scrolling

- [ ] Final smoke test: `uv pip install reel-vcr && reel --help` in a fresh venv on one of the three machines.
- [ ] Push the `v0.1.0` tag. Verify the GitHub release page is generated and the artifact is attached.
- [ ] Update README badges (CI, license, Python, PyPI version). The PyPI badge should now resolve to a real version.

### 9:00am PT — Show HN

- [ ] Submit `show-hn.md` to Hacker News at exactly **9:00am PT Tuesday**. This is the sweet spot — US engineers are at their desks, EU folks are still active, lunch in Asia. **Tuesday > Monday** (Monday is full of weekend backlog); **Tuesday > Wednesday/Thursday** (peak HN traffic).
- [ ] Pin the HN URL in a private note. Refresh once at 9:15 to confirm it's live; then leave it alone for an hour. Repeatedly reloading the front page does not help.

### 9:05am PT — fan out

- [ ] Publish the Twitter thread (already scheduled).
- [ ] Publish the Bluesky thread.
- [ ] Submit the r/Python post.
- [ ] Submit the r/LocalLLaMA post.
- [ ] **Hold the r/MachineLearning post** until 10:30am PT — it's a tougher audience and a small initial bump in stars/comments from HN helps the post survive their moderation.

### 9:30am PT — maintainer outreach (P1 round)

- [ ] Send the LangChain DM (Harrison Chase).
- [ ] Send the LlamaIndex DM (Jerry Liu).
- [ ] Send the dspy DM (Omar Khattab).
- [ ] Send the instructor DM (Jason Liu).
- [ ] Send the Vercel AI SDK DM.
- [ ] Personalize each one — drop a one-liner referencing something they shipped this month. The templates in `maintainer-outreach.md` are scaffolds, not finished sends.

### 10:00am PT — newsletter outreach (P1 round)

- [ ] Email / DM the P1 contacts in `outreach.csv`: Latent Space, TLDR AI, Python Weekly, PyCoder's Weekly.
- [ ] Each one: 3 sentences, the HN link, the repo link, one specific reason their audience cares.

### 10:30am PT — second wave

- [ ] Submit r/MachineLearning post.
- [ ] If the HN post is on the front page (top 30), do not engage further with social. Stay on HN comments.

### All day — comment hygiene

- [ ] Refresh the HN thread every ~15 minutes. **Respond to every top-level comment within 30 minutes** while the post is live. This is the single biggest signal of an author who cares — and HN ranking explicitly rewards engaged authors.
- [ ] Don't argue. If someone is wrong, thank them and clarify once. If they're still wrong, let it go.
- [ ] Reply to GitHub issues as they come in. Even a "thanks, looking now" within an hour is the difference between a contributor staying and leaving.
- [ ] If the install breaks for anyone, fix and ship a patch release within 2 hours. Pin the workaround in the issue.

### 2:00pm PT — newsletter outreach (P2/P3 round)

- [ ] Email / DM remaining contacts in `outreach.csv` (P2 and P3).
- [ ] These are slower-burn placements — no expectation of same-day pickup.

### 5:00pm PT — recap

- [ ] Take a screenshot of the HN ranking. (For your own records, not for further posting.)
- [ ] Note total stars / issues / PRs at end-of-day in `docs/launch-metrics.md` (create the file). This is useful baseline data for the *next* launch, not vanity.

### 9:00pm PT — close the laptop

- [ ] Set notifications to do-not-disturb. The internet will still be there tomorrow.
- [ ] Tomorrow's TODO: triage any issue that came in overnight, reply to newsletter editors who responded, write a "launch retro" post in `docs/`.

---

## Things that must be true *before* the HN post goes live

- [ ] Repo is public.
- [ ] README renders correctly on GitHub (no broken images, no broken anchor links).
- [ ] License file is present and visible.
- [ ] CI is green on `main`.
- [ ] PyPI install works in a clean venv.
- [ ] Issue templates exist.
- [ ] At least one reviewer outside of yourself has tried the quickstart and confirmed it works.
- [ ] The 60-second demo GIF actually plays on GitHub's README renderer (test it in incognito).

## Things to NOT do on launch day

- Do not push code changes between 9am and 5pm PT unless they're fixing a launch-day bug. A README typo can wait.
- Do not add a "Sponsor" button or any monetization signal. It tanks Show HN trust instantly.
- Do not edit the HN title after submission (HN locks it after ~2h anyway).
- Do not cross-post the HN comment thread to Twitter ("look at all this engagement!"). It reads as desperate.
- Do not announce on LinkedIn unless your audience is genuinely there — the tonal mismatch is severe.
- Do not say "we" — the README is honest that this is a solo project; the posts should be too.

---

## If the launch underperforms

- HN is lottery-shaped. A "good" project gets one shot at the front page; a "great" project gets two or three. If you didn't make the front page, the post still indexes well in Google. Don't repost the same submission within 30 days — HN's algorithm penalizes it.
- The Twitter / Bluesky / Reddit threads outlive the HN post by weeks. Pin the Twitter thread to your profile.
- The newsletter outreach is the slow burn. Pickups land 1-3 weeks later. Don't measure success at end-of-day.
