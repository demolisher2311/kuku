# Judge vs human: 38 clips rated blind by the reviewer

Model: `openai:gpt-4.1-mini`. Both judges see exactly the clip script the human saw. 'Judge yes' = score >= 7. 'Approved' = hook + cliffhanger + coherence >= 22 and hook >= 7 (same rule for both judges).

## Agreement per criterion

| Criterion | Judge | Judge yes | Human yes | Agreement | Judge yes, human no |
|---|---|---|---|---|---|
| hook | classic (old) | 35/38 | 28/38 | 76% | 8 |
| hook | strict (new) | 31/38 | 28/38 | 82% | 5 |
| cliffhanger | classic (old) | 35/37 | 24/37 | 65% | 12 |
| cliffhanger | strict (new) | 32/37 | 24/37 | 68% | 10 |
| standalone | classic (old) | 26/37 | 32/37 | 62% | 4 |
| standalone | strict (new) | 37/37 | 32/37 | 86% | 5 |

## Does the judge's total score track the human verdict?

| Judge | Rank correlation with human points | Avg total: human Good | human OK | human Bad |
|---|---|---|---|---|
| classic (old) | +0.12 | 22.4 | 22.5 | 21.5 |
| strict (new) | +0.34 | 26.2 | 25.3 | 23.5 |

## If we only posted approved clips

| Judge | Approved | Of those, human Good | human Bad | Human Good clips it rejected |
|---|---|---|---|---|
| classic (old) | 24/38 | 11 | 3 | 6 |
| strict (new) | 29/38 | 15 | 4 | 2 |

## Per clip

| Clip | Source | Human | Old judge h/c/s | New judge h/c/s | New approved |
|---|---|---|---|---|---|
| v1 E03-R1.3 | ai_top | bad | 7/8/6 | 4/9/8 | no |
| v1 E03-R2.1 | ai_top | good | 8/8/7 | 9/9/9 | yes |
| v1 E46-H1 | baseline | bad | 7/8/6 | 9/9/9 | yes |
| v1 E11-P3 | ai_top | ok | 7/8/6 | 9/9/9 | yes |
| v1 E37-P2a | ai_top | bad | 8/7/7 | 10/9/9 | yes |
| v1 E47-R2.1 | ai_top | good | 7/8/7 | 9/9/9 | yes |
| v1 E25-R2.2 | ai_low | good | 6/7/7 | 5/9/9 | no |
| v1 E42-H1 | baseline | good | 8/7/7 | 9/6/9 | yes |
| v1 E39-P1 | ai_low | bad | 7/8/6 | 8/8/9 | yes |
| v1 E29-H2 | baseline | good | 7/8/6 | 9/8/9 | yes |
| v1 E43-R2.1 | ai_low | ok | 6/7/5 | 5/8/8 | no |
| v1 E46-R1.3 | ai_low | good | 8/9/7 | 5/7/8 | no |
| v1 E11-H1 | baseline | good | 7/8/7 | 9/9/9 | yes |
| v1 E21-H1 | baseline | bad | 7/6/7 | 8/4/9 | no |
| v1 E01-R1.1 | ai_top | ok | 8/9/8 | 8/9/9 | yes |
| v1 E02-R1.1 | ai_top | ok | 8/9/8 | 8/9/9 | yes |
| v1 E35-H1 | baseline | good | 7/9/7 | 9/9/9 | yes |
| v1 E01-R2.1 | ai_top | ok | 8/9/8 | 9/9/9 | yes |
| v1 E03-H2 | baseline | ok | 8/8/7 | 9/9/9 | yes |
| v1 E01-R1.4 | ai_low | bad | 8/9/7 | 9/9/9 | yes |
| v1 E01-R1.2 | ai_top | good | 8/9/7 | 10/9/9 | yes |
| v1 E03-H1 | baseline | good | 7/8/6 | 9/9/9 | yes |
| v1 E23-P2 | ai_top | good | 8/9/7 | 10/9/9 | yes |
| v2 E02-H2 | baseline | ok | 8/7/7 | 9/9/9 | yes |
| v2 E10-P4 | ai_top | good | 7/8/6 | 8/9/9 | yes |
| v2 E11-R2.1 | ai_top | ok | 7/8/7 | 8/9/9 | yes |
| v2 E03-R2.1 | ai_top | ok | 7/9/7 | 4/9/9 | no |
| v2 E31-R2.3 | ai_top | bad | 8/7/7 | 6/6/9 | no |
| v2 E01-R1.1 | ai_top | ok | 8/9/9 | 8/9/9 | yes |
| v2 E11-P2 | ai_top | good | 8/9/7 | 9/9/9 | yes |
| v2 E12-R2.1 | ai_top | ok | 8/9/7 | 9/9/9 | yes |
| v2 E29-R1.1 | ai_top | good | 7/8/6 | 9/9/9 | yes |
| v2 E05-H2 | baseline | ok | 3/6/5 | 8/5/8 | no |
| v2 E28-H1 | baseline | good | 7/9/8 | 9/9/9 | yes |
| v2 E05-H1 | baseline | ok | 8/9/7 | 8/9/9 | yes |
| v2 E19-R2.2 | ai_top | bad | 7/8/6 | 5/5/8 | no |
| v2 E44-H1 | baseline | good | 7/8/6 | 9/9/9 | yes |
| v2 E17-P4 | ai_top | good | 8/9/7 | 9/9/9 | yes |
