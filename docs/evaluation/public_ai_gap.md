# Public AI gap: writers on the same split

Generated 2026-11-02T04:38:31Z by scripts/v2/public_ai_gap.py; audit runs val-judge-v1-h45, val-judge-v2-h45, val-judge-v2-h55, val-judge-v2-h55b, val-judge-v2-glm53, val-judge-v2-glm53-low, val-judge-v2-gemma4, val-judge-v2-gemma4-nothink. Same prompts and gates for every writer; temperature 0 where the endpoint takes it. SUPPORTS and ANSWERS are the audit panel's final verdicts (no judge from the writer's family). Rates are over items answered without an error. Every writer ran with a 60 s timeout; Over 20 s is the share of writer calls slower than production's generation cap, which in production would show the record without an answer.

| Writer | Licence | Where it can run | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused | State accuracy | p50 / p95 s | Over 20 s | USD per answer | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | proprietary (API only) | API only | 1.000 (193/193) | 0.095 (4/42) | 0.400 (32/80) | 0.900 (54/60) | 0.671 (94/140) | 3.2 / 9.2 | 0.016 (1/64) | 0.0244 | 0 |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | proprietary (API only) | API only | 0.987 (154/156) | 0.075 (3/40) | 0.412 (33/80) | 0.900 (54/60) | 0.614 (86/140) | 3.2 / 10.0 | 0.000 (0/64) | 0.0071 | 0 |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | proprietary (API only) | API only | 0.975 (158/162) | 0.026 (1/39) | 0.463 (37/80) | 0.950 (57/60) | 0.514 (72/140) | 4.4 / 11.2 | 0.000 (0/64) | 0.0012 | 0 |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | GLM-5.3 licence (MIT terms plus a Model-as-a-Service clause: operators over USD 10B revenue need Z.AI's security review) | multi-GPU node (753B parameters; FP8 weights about 750 GB): not one 96 GB GPU, not two 80 GB GPUs | 1.000 (70/70) | 0.042 (1/24) | 0.547 (29/53) | 1.000 (52/52) | 0.667 (70/105) | 1.0 / 11.6 | 0.219 (14/64) | 0.0113 | 35 |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | GLM-5.3 licence (MIT terms plus a Model-as-a-Service clause: operators over USD 10B revenue need Z.AI's security review) | multi-GPU node (753B parameters; FP8 weights about 750 GB): not one 96 GB GPU, not two 80 GB GPUs | 1.000 (167/167) | 0.024 (1/41) | 0.450 (36/80) | 0.967 (58/60) | 0.586 (82/140) | 1.6 / 8.8 | 0.016 (1/64) | 0.0082 | 0 |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | Apache 2.0 | one 96 GB GPU (BF16 about 52 GB); laptop with a 4-bit quantization (about 16 GB) | 1.000 (11/11) | 0.000 (0/6) | 0.771 (27/35) | 1.000 (54/54) | 0.629 (56/89) | 0.7 / 35.5 | 0.969 (62/64) | 0.0010 | 51 |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | Apache 2.0 | one 96 GB GPU (BF16 about 52 GB); laptop with a 4-bit quantization (about 16 GB) | 1.000 (141/141) | 0.079 (3/38) | 0.438 (35/80) | 0.900 (54/60) | 0.586 (82/140) | 1.7 / 18.0 | 0.078 (5/64) | 0.0006 | 0 |

## Expected state: CONFLICTING

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 1 | - | - | 1.000 (1/1) | - |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 1 | - | - | 1.000 (1/1) | - |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 1 | - | - | 1.000 (1/1) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 1 | - | - | 1.000 (1/1) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 1 | - | - | 1.000 (1/1) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 1 | - | - | 1.000 (1/1) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 1 | - | - | 1.000 (1/1) | - |

## Expected state: INCOMPARABLE

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 6 | 1.000 (2/2) | 1.000 (1/1) | - | 0.833 (5/6) |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 6 | 1.000 (2/2) | 1.000 (1/1) | - | 0.833 (5/6) |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 6 | - | - | - | 1.000 (6/6) |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 6 | - | - | - | 1.000 (5/5) |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 6 | - | - | - | 1.000 (6/6) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 6 | - | - | - | 1.000 (5/5) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 6 | 1.000 (1/1) | - | - | 0.833 (5/6) |

## Expected state: INSUFFICIENT_EVIDENCE

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 44 | 1.000 (11/11) | 0.500 (2/4) | - | 0.886 (39/44) |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 44 | 1.000 (12/12) | 0.333 (1/3) | - | 0.886 (39/44) |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 44 | 0.857 (12/14) | 0.000 (0/1) | - | 0.932 (41/44) |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 44 | - | - | - | 1.000 (38/38) |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 44 | 1.000 (9/9) | 0.000 (0/2) | - | 0.955 (42/44) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 44 | - | - | - | 1.000 (39/39) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 44 | 1.000 (14/14) | 0.000 (0/1) | - | 0.886 (39/44) |

## Expected state: PARTIALLY_SUPPORTED

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 6 | 1.000 (4/4) | 0.000 (0/1) | 0.500 (3/6) | - |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 6 | 0.750 (3/4) | 0.000 (0/2) | 0.500 (3/6) | - |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 6 | 1.000 (2/2) | 0.000 (0/1) | 0.833 (5/6) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 6 | - | - | 1.000 (3/3) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 6 | 1.000 (1/1) | 0.000 (0/1) | 0.833 (5/6) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 6 | 1.000 (1/1) | 0.000 (0/1) | 0.750 (3/4) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 6 | 1.000 (1/1) | 0.000 (0/1) | 0.667 (4/6) | - |

## Expected state: RESTRICTED

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 10 | - | - | - | 1.000 (10/10) |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 10 | - | - | - | 1.000 (10/10) |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 10 | - | - | - | 1.000 (10/10) |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 10 | - | - | - | 1.000 (9/9) |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 10 | - | - | - | 1.000 (10/10) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 10 | - | - | - | 1.000 (10/10) |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 10 | - | - | - | 1.000 (10/10) |

## Expected state: SUPPORTED

| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4-5-20251001 (val-v1-h45: v1-claude-haiku-4-5) | 73 | 1.000 (176/176) | 0.028 (1/36) | 0.384 (28/73) | - |
| claude-haiku-4-5-20251001 (val-v2-h45: v2-claude-haiku-4-5) | 73 | 0.993 (137/138) | 0.029 (1/34) | 0.397 (29/73) | - |
| claude-haiku-5-5 (val-v2-h55: v2-claude-haiku-5-5-low) | 73 | 0.986 (144/146) | 0.027 (1/37) | 0.425 (31/73) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53: v2-cf_zai-org_glm-5.3) | 73 | 1.000 (70/70) | 0.042 (1/24) | 0.510 (25/49) | - |
| @cf/zai-org/glm-5.3 (val-v2-glm53-low: v2-cf_zai-org_glm-5.3-xa8da54bc) | 73 | 1.000 (157/157) | 0.026 (1/38) | 0.411 (30/73) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4: v2-cf_google_gemma-4-26b-a4b-it) | 73 | 1.000 (10/10) | 0.000 (0/5) | 0.767 (23/30) | - |
| @cf/google/gemma-4-26b-a4b-it (val-v2-gemma4-nothink: v2-cf_google_gemma-4-26b-a4b-it-xddfbc286) | 73 | 1.000 (125/125) | 0.083 (3/36) | 0.411 (30/73) | - |
