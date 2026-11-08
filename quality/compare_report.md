# Before vs after: `outputs/openai_gpt-4.1-mini_full` -> `outputs/openai_gpt-4.1-mini_v2`

## 1. Output shape (distinct promos, near-duplicates removed)

| | Before | After |
|---|---|---|
| Valid candidates | 300 | 209 |
| Distinct promos | 116 | 95 |
| Valid on first try | 91/200 | 41/200 |
| Median length | 39.8s | 47.3s |
| Under 35s | 42% (49/116) | 0% (0/95) |
| 45s or longer | 38% (44/116) | 55% (52/95) |
| Top 20: 45s or longer | 55% (11/20) | 70% (14/20) |
| Top 20: under 35s | 25% (5/20) | 0% (0/20) |
| Finder LLM calls: new / served from cache | 50 / 142 | 180 / 12 |

## 2. Where the clips you rated land (proxy, matched by >= 50% overlap)

| Rated clip | Group | Length | Your verdict | Rank before | Rank after |
|---|---|---|---|---|---|
| E03-R2.1 | ai_top | 54s | good | 6 | 56 |
| E47-R2.1 | ai_top | 46s | good | 5 | 80 |
| E25-R2.2 | ai_low | 46s | good | 62 | 66 |
| E42-H1 | baseline | 55s | good | 19 | 95 |
| E29-H2 | baseline | 52s | good | 41 | 76 |
| E46-R1.3 | ai_low | 26s | good | 88 | 68 |
| E11-H1 | baseline | 55s | good | 16 | 6 |
| E35-H1 | baseline | 55s | good | 45 | 43 |
| E01-R1.2 | ai_top | 53s | good | 4 | 17 |
| E03-H1 | baseline | 28s | good | not found | 56 |
| E23-P2 | ai_top | 53s | good | 3 | 12 |
| E11-P3 | ai_top | 41s | ok | 9 | 1 |
| E43-R2.1 | ai_low | 27s | ok | 105 | 40 |
| E01-R1.1 | ai_top | 30s | ok | 1 | 5 |
| E02-R1.1 | ai_top | 28s | ok | 7 | 19 |
| E01-R2.1 | ai_top | 32s | ok | 2 | 17 |
| E03-H2 | baseline | 46s | ok | 6 | 56 |
| E03-R1.3 | ai_top | 47s | bad | 10 | not found |
| E46-H1 | baseline | 49s | bad | 88 | 68 |
| E37-P2a | ai_top | 21s | bad | 8 | not found |
| E39-P1 | ai_low | 20s | bad | 83 | not found |
| E21-H1 | baseline | 36s | bad | 17 | 21 |
| E01-R1.4 | ai_low | 24s | bad | 70 | not found |

Rated clips that land in the top 20:

- **before**: 14 clips, 6 Good, 3 Bad, avg points 1.21
- **after**: 7 clips, 3 Good, 0 Bad, avg points 1.43
