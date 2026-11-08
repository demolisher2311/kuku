# Judge vs human: 38 clips rated blind, 136 Good-vs-Bad pairs

Each judge sees exactly the clip script the human saw. Score judges: 'yes' = score >= 7.

## gemini:gemini-3.5-flash-lite

| Judge | Picks the clip you rated Good (over the Bad one) | Failed calls |
|---|---|---|
| classic (1-10 scores; tie = half) | 71% (96/136) | 0 |
| strict (1-10 scores; tie = half) | 64% (87.5/136) | 0 |
| pairwise (A/B) | 76% (103/135) | 1 |

Position bias: the pairwise judge picked Clip A in 53% (72/135) of comparisons (the Good clip was A in 57% (77/136)).

| Criterion | classic agrees | strict agrees | pairwise fact check agrees |
|---|---|---|---|
| hook | 74% (28/38) | 68% (26/38) | (compared via better_hook, not per clip) |
| cliffhanger | 65% (24/37) | 59% (22/37) | 79% (19/24) (not resolved = cliffhanger) |
| standalone | 70% (26/37) | 84% (31/37) | 88% (21/24) |

- classic: totals range 13-26 of 30; 0/38 clips got 9+ on everything
- strict: totals range 15-27 of 30; 1/38 clips got 9+ on everything

## openai:gpt-4.1-mini (from cache; pairwise not run on this model)

| Judge | Picks the clip you rated Good (over the Bad one) | Failed calls |
|---|---|---|
| classic (1-10 scores; tie = half) | 68% (92.5/136) | 0 |
| strict (1-10 scores; tie = half) | 69% (94/136) | 0 |

| Criterion | classic agrees | strict agrees | pairwise fact check agrees |
|---|---|---|---|
| hook | 76% (29/38) | 82% (31/38) | (compared via better_hook, not per clip) |
| cliffhanger | 65% (24/37) | 68% (25/37) | n/a |
| standalone | 62% (23/37) | 86% (32/37) | n/a |

- classic: totals range 14-26 of 30; 0/38 clips got 9+ on everything
- strict: totals range 18-28 of 30; 20/38 clips got 9+ on everything

API usage (gemini:gemini-3.5-flash-lite): 211 calls, 0 cached, tokens in 401,161, out 50,883, thinking 0
