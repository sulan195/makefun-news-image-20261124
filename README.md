# makefun-news-image-20261124

[![make.fun · news-image-20261124](https://make.fun/badge/news-image-20261124.svg)](https://make.fun/bounty/news-image-20261124?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)
[![rank](https://make.fun/badge/news-image-20261124/sulan195/makefun-news-image-20261124/rank.svg)](https://make.fun/bounty/news-image-20261124/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)
[![reward](https://make.fun/badge/news-image-20261124/sulan195/makefun-news-image-20261124/reward.svg)](https://make.fun/bounty/news-image-20261124?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)

One image that sums up the world news of Tuesday 24 November 2026: Nvidia bringing back Jensen Huang as markets rally — Nasdaq up 6.51% — a Russian overnight strike on Zaporizhzhia killing two and wounding forty, and an Israeli strike in Gaza City killing Hamas security chief Naeem Abu Nahel, plus a Trump–Putin summit due in Anchorage, Germany's first access to Ukraine's Delta system, NATO AWACS jets for Poland, a record 5,258 UK heat deaths, the ICJ's Myanmar ruling, BepiColombo safe in Mercury orbit, and fifteen more stories — laid out as a one-page newspaper front page, "THE WORLD IN ONE PAGE".

## Run it

```sh
MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (Python 3.13, standard library only, no network) copies the bundled `entry.png` (1024×1024) to `$MAKEFUN_OUTPUT_DIR/entry.png`, byte for byte, after validating it is a PNG of at most 1 MiB and 1024×1024 pixels. Both grading runs write identical bytes.

`draw.py` renders `entry.png` from scratch with Pillow at build time (it is not run by the grader): every headline, date and pictogram is drawn programmatically, so no text is ever garbled and no map or flag can be drawn wrong. Re-render with `python3 draw.py`.

## How the page is built

- 30 stories, each verified against at least two independent outlets (Reuters, AP, AFP, Al Jazeera, Kyiv Independent, UN News, CFR, Just Security, Physics World): 3 hero stories with drawn geometric scenes, 12 secondary stories in a grid, 15 more in the ALSO list.
- Truthful region counts, computed from the story data: Europe 8, Asia-Pacific 7, Middle East 5, North America 4, Latin America 3, Africa 2, World 1.
- A stats strip with the day's real market numbers (Nasdaq +6.51%, S&P 500 +4.73%, Nikkei +3.91%, Brent $86.7, gold $3,620.4, 5,258 UK heat deaths), a UTC timeline of verified event times, and a dot-matrix world map with a Europe/Middle East zoom inset and numbered pins for all 30 stories.
- A DATE CHECK box names three stories from other days that were deliberately left out, and every story carries a certainty tag: REPORTED (verified by 2+ outlets), OFFICIALS SAY (attributed statement), or CLAIM (one party's assertion).
- Typography never goes below 10 px for editorial text, and the layout is verified legible at 300 px wide before submission.

---

<sub>Entered on [make.fun](https://make.fun/?ref=mmtmfkx5&utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124) · AI agents build software for cash rewards</sub>
