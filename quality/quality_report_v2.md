# Quality check: human review

Blind review of 15 clips (source hidden while rating). Sheet: `quality/review_sheet_v2.xlsx`.

## 1. Human verdict by source

| Group | Clips | Good | Good or OK | Avg points (Good=2, OK=1, Bad=0) |
|---|---|---|---|---|
| AI tool: top-ranked | 10 | 40% (4/10) | 80% (8/10) | 1.20 |
| Keyword baseline (no AI) | 5 | 40% (2/5) | 100% (5/5) | 1.40 |

### Verdict by clip length (all sources)

| Length | Clips | Good | Avg points |
|---|---|---|---|
| 20-35s | 1 | 100% (1/1) | 2.00 |
| 35-45s | 5 | 40% (2/5) | 1.20 |
| 45-60s | 9 | 33% (3/9) | 1.22 |

## 2. Which rule fails most (Y rate per criterion)

| Criterion | AI top | AI low | Baseline |
|---|---|---|---|
| hook | 60% (6/10) | n/a | 80% (4/5) |
| cliffhanger | 70% (7/10) | n/a | 60% (3/5) |
| standalone | 90% (9/10) | n/a | 80% (4/5) |
| clean_cut | n/a | n/a | n/a |

## 3. Does the AI judge agree with you? (judge 'yes' = score >= 7)

| Criterion | Agreement | Judge said yes, you said no (judge too generous) |
|---|---|---|
| hook | 60% (6/10) | 4 |
| cliffhanger | 70% (7/10) | 3 |
| standalone | 90% (9/10) | 1 |
| clean_cut | n/a | 0 |

## 5. Clips you rated Bad

- **ai_top** E31-R2.3 (tool rank 10, E31 00:06.90-01:05.50): (no note)
- **ai_top** E19-R2.2 (tool rank 9, E19 01:10.60-01:49.80): (no note)
