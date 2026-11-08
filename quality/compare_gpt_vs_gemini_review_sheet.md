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
| E03-R2.1 | ai_top | 54s | good | 63 | 76 |
| E47-R2.1 | ai_top | 46s | good | 82 | 64 |
| E25-R2.2 | ai_low | 46s | good | 81 | not found |
| E42-H1 | baseline | 55s | good | 92 | 60 |
| E29-H2 | baseline | 52s | good | 64 | 49 |
| E46-R1.3 | ai_low | 26s | good | 29 | not found |
| E11-H1 | baseline | 55s | good | 23 | 74 |
| E35-H1 | baseline | 55s | good | 71 | 26 |
| E01-R1.2 | ai_top | 53s | good | 5 | 57 |
| E03-H1 | baseline | 28s | good | 63 | 18 |
| E23-P2 | ai_top | 53s | good | 27 | 5 |
| E11-P3 | ai_top | 41s | ok | 24 | 8 |
| E43-R2.1 | ai_low | 27s | ok | 50 | 36 |
| E01-R1.1 | ai_top | 30s | ok | 20 | 16 |
| E02-R1.1 | ai_top | 28s | ok | 6 | 27 |
| E01-R2.1 | ai_top | 32s | ok | 20 | 16 |
| E03-H2 | baseline | 46s | ok | 63 | 76 |
| E03-R1.3 | ai_top | 47s | bad | not found | 18 |
| E46-H1 | baseline | 49s | bad | 29 | 51 |
| E37-P2a | ai_top | 21s | bad | not found | 48 |
| E39-P1 | ai_low | 20s | bad | 13 | 85 |
| E21-H1 | baseline | 36s | bad | 2 | 63 |
| E01-R1.4 | ai_low | 24s | bad | 5 | not found |

Rated clips that land in the top 20:

- **before**: 7 clips, 1 Good, 3 Bad, avg points 0.71
- **after**: 6 clips, 2 Good, 1 Bad, avg points 1.17
