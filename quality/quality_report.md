# Quality check: human review

Blind review of 23 clips (source hidden while rating). Sheet: `quality/review_sheet.xlsx`.

## 1. Human verdict by source

| Group | Clips | Good | Good or OK | Avg points (Good=2, OK=1, Bad=0) |
|---|---|---|---|---|
| AI tool: top-ranked | 10 | 40% (4/10) | 80% (8/10) | 1.20 |
| AI tool: bottom half | 5 | 40% (2/5) | 60% (3/5) | 1.00 |
| Keyword baseline (no AI) | 8 | 62% (5/8) | 75% (6/8) | 1.38 |

### Verdict by clip length (all sources)

| Length | Clips | Good | Avg points |
|---|---|---|---|
| 20-35s | 9 | 22% (2/9) | 0.89 |
| 35-45s | 2 | 0% (0/2) | 0.50 |
| 45-60s | 12 | 75% (9/12) | 1.58 |

## 2. Which rule fails most (Y rate per criterion)

| Criterion | AI top | AI low | Baseline |
|---|---|---|---|
| hook | 70% (7/10) | 60% (3/5) | 100% (8/8) |
| cliffhanger | 60% (6/10) | 60% (3/5) | 71% (5/7) |
| standalone | 90% (9/10) | 60% (3/5) | 100% (7/7) |
| clean_cut | n/a | n/a | n/a |

## 3. Does the AI judge agree with you? (judge 'yes' = score >= 7)

| Criterion | Agreement | Judge said yes, you said no (judge too generous) |
|---|---|---|
| hook | 53% (8/15) | 3 |
| cliffhanger | 60% (9/15) | 5 |
| standalone | 67% (10/15) | 0 |
| clean_cut | n/a | 0 |

## 4. Recall: did the tool find your pick? (match = overlap >= 50%)

| Episode | Your clip | AI best match | Overlap | AI rank | Baseline overlap |
|---|---|---|---|---|---|
| 7 | 00:45.2-01:15.5 | E07-P1 E07 00:21.00-01:05.20 | 66% ✓ | 14 | 86% |
| 27 | 01:50.3-02:12.6 | E27-R1.3 E27 01:50.20-02:30.50 | 100% ✓ | 61 | 64% |

**AI found 2/2 of your picks.**

## 5. Clips you rated Bad

- **ai_top** E03-R1.3 (tool rank 10, E03 01:38.40-02:25.75): (no note)
- **baseline** E46-H1 (tool rank 9, E46 00:37.00-01:25.80): good scene but not much, no cliff hanger
- **ai_top** E37-P2a (tool rank 8, E37 01:35.50-01:56.50): (no note)
- **ai_low** E39-P1 (tool rank 83, E39 00:29.60-00:50.00): so random and short.
- **baseline** E21-H1 (tool rank 8, E21 00:31.00-01:06.80): it is good but not for promo
- **ai_low** E01-R1.4 (tool rank 70, E01 01:47.40-02:11.30): (no note)
