# Before vs after: `outputs/openai_gpt-4.1-mini_v3_strict` -> `outputs/gemini-3.5-flash-lite_pairwise`

## 1. Output shape (distinct promos, near-duplicates removed)

| | Before | After |
|---|---|---|
| Valid candidates | 209 | 167 |
| Distinct promos | 95 | 85 |
| Valid on first try | 41/200 | 54/200 |
| Median length | 47.3s | 47.7s |
| Under 35s | 0% (0/95) | 0% (0/85) |
| 45s or longer | 57% (54/95) | 60% (51/85) |
| Top 20: 45s or longer | 90% (18/20) | 50% (10/20) |
| Top 20: under 35s | 0% (0/20) | 0% (0/20) |
| Finder LLM calls: new / served from cache | 0 / 142 | 0 / 132 |

## 2. Where the clips you rated land (proxy, matched by >= 50% overlap)

| Rated clip | Group | Length | Your verdict | Rank before | Rank after |
|---|---|---|---|---|---|
| E10-P4 | ai_top | 48s | good | 23 | 74 |
| E11-P2 | ai_top | 47s | good | 7 | not found |
| E29-R1.1 | ai_top | 41s | good | not found | 49 |
| E28-H1 | baseline | 38s | good | 75 | 20 |
| E44-H1 | baseline | 24s | good | 51 | not found |
| E17-P4 | ai_top | 60s | good | 10 | 21 |
| E02-H2 | baseline | 52s | ok | 6 | 27 |
| E11-R2.1 | ai_top | 49s | ok | 24 | 8 |
| E03-R2.1 | ai_top | 60s | ok | 30 | 45 |
| E01-R1.1 | ai_top | 39s | ok | 20 | 16 |
| E12-R2.1 | ai_top | 52s | ok | 8 | 2 |
| E05-H2 | baseline | 53s | ok | 44 | 43 |
| E05-H1 | baseline | 38s | ok | 4 | 58 |
| E31-R2.3 | ai_top | 59s | bad | 72 | not found |
| E19-R2.2 | ai_top | 39s | bad | not found | not found |

Rated clips that land in the top 20:

- **before**: 6 clips, 2 Good, 0 Bad, avg points 1.33
- **after**: 4 clips, 1 Good, 0 Bad, avg points 1.25
