# Scam shield hold-out benchmark

Protocol: rules frozen first, then 60 invoices (30 genuine, 30 scam) written in English, Malay, Bangla and Chinese. Not tuned on this set. Synthetic samples — see sudoroute/benchmark/invoice_holdout.py.

| | Detection (REVIEW or BLOCK) | Hard block | False block (genuine) | False alarm (genuine) |
|---|---|---|---|---|
| **All** | 100.0% | 60.0% | 0.0% | 0.0% |
| English | 100.0% | 61.1% | 0.0% | 0.0% |
| Malay | 100.0% | 50.0% | 0.0% | 0.0% |
| Bangla | 100.0% | 75.0% | 0.0% | 0.0% |
| Chinese | 100.0% | 50.0% | 0.0% | 0.0% |

## Hold-out v2 (unseen; includes scams built to beat the negation rule)

Written after the negation-aware warning rule was added (which was a response to v1's false alarms), evaluated once. Includes scams designed to beat that rule.

Detection 100.0% · hard block 8.3% · false block 0.0% · false alarm 16.7% (2/12 genuine sent to review)

History: with the original frozen rules, set v1 had 13.3% false alarms. v1 result with the original frozen rules. The current v1 numbers are measured after a rule change made in response to v1, so v1 is no longer unseen.

| ID | Lang | Label | Verdict | Score | Signals | Note |
|---|---|---|---|---|---|---|
| V2-G01 | en | genuine | SAFE | 0 | — | warning in a footer |
| V2-G02 | en | genuine | SAFE | 0 | — | warning with 'only' in a separate clause |
| V2-G03 | en | genuine | REVIEW | 30 | unusual_method | FAQ-style warning |
| V2-G04 | en | genuine | SAFE | 0 | — | scholarship + warning |
| V2-G05 | ms | genuine | SAFE | 0 | — | Malay warning |
| V2-G06 | ms | genuine | SAFE | 0 | — | Malay 'jangan' warning |
| V2-G07 | bn | genuine | SAFE | 0 | — | Bangla warning |
| V2-G08 | bn | genuine | SAFE | 0 | — | Bangla personal-account warning |
| V2-G09 | zh | genuine | SAFE | 0 | — | Chinese warning |
| V2-G10 | zh | genuine | SAFE | 0 | — | Chinese personal-account warning |
| V2-G11 | en | genuine | SAFE | 0 | — | plain invoice, no warning |
| V2-G12 | en | genuine | REVIEW | 30 | unusual_method | genuine 'gift card' mention about bookshop |
| V2-S01 | en | scam | REVIEW | 30 | unusual_method | negation trick with a dash |
| V2-S02 | en | scam | REVIEW | 30 | unusual_method | negation trick with 'instead' |
| V2-S03 | en | scam | REVIEW | 30 | unusual_method | fake warning followed by request |
| V2-S04 | en | scam | REVIEW | 30 | unusual_method | personal account 'not the old one' |
| V2-S05 | ms | scam | REVIEW | 30 | unusual_method | Malay negation trick |
| V2-S06 | ms | scam | REVIEW | 30 | unusual_method | Malay personal account |
| V2-S07 | bn | scam | REVIEW | 30 | unusual_method | Bangla negation trick |
| V2-S08 | bn | scam | REVIEW | 30 | unusual_method | Bangla personal account |
| V2-S09 | zh | scam | REVIEW | 30 | unusual_method | Chinese negation trick |
| V2-S10 | zh | scam | REVIEW | 30 | unusual_method | Chinese personal account |
| V2-S11 | en | scam | BLOCK | 80 | lookalike_domain, bank_mismatch | look-alike sender + new account (classic) |
| V2-S12 | en | scam | REVIEW | 40 | prompt_injection, hidden_content | hidden AI instruction inside a warning |

## Set v1 samples

| ID | Lang | Label | Verdict | Score | Signals | Note |
|---|---|---|---|---|---|---|
| G01 | en | genuine | SAFE | 0 | — | plain semester invoice |
| G02 | en | genuine | SAFE | 0 | — | plain term invoice |
| G03 | en | genuine | SAFE | 0 | — | US invoice |
| G04 | en | genuine | SAFE | 0 | — | AU invoice |
| G05 | en | genuine | SAFE | 0 | — | official subdomain sender |
| G06 | en | genuine | SAFE | 10 | urgency | genuine overdue notice with 'FINAL NOTICE' |
| G07 | en | genuine | SAFE | 0 | — | warns students NOT to pay in crypto (trap) |
| G08 | en | genuine | SAFE | 0 | — | partial balance after scholarship |
| G09 | en | genuine | SAFE | 0 | — | instalment 2 of 3 |
| G10 | en | genuine | SAFE | 0 | — | high-end fee within range |
| G11 | en | genuine | SAFE | 0 | — | low-end fee |
| G12 | en | genuine | SAFE | 0 | — | reminder wording 'please pay today' |
| G13 | en | genuine | SAFE | 0 | — | mentions visa compliance politely (trap) |
| G14 | en | genuine | SAFE | 0 | — | accommodation + tuition statement |
| G15 | en | genuine | SAFE | 0 | — | invoice with student number missing |
| G16 | ms | genuine | SAFE | 0 | — | Malay invoice |
| G17 | ms | genuine | SAFE | 10 | urgency | Malay with 'segera' (trap) |
| G18 | ms | genuine | SAFE | 0 | — | Malay warning against personal accounts (trap) |
| G19 | ms | genuine | SAFE | 0 | — | Malay instalment offer |
| G20 | ms | genuine | SAFE | 0 | — | Malay statement with hostel |
| G21 | bn | genuine | SAFE | 0 | — | Bangla info sheet for BD students |
| G22 | bn | genuine | SAFE | 0 | — | Bangla reminder with deadline |
| G23 | bn | genuine | SAFE | 0 | — | Bangla warning about scams (trap) |
| G24 | bn | genuine | SAFE | 0 | — | Bangla instalment |
| G25 | zh | genuine | SAFE | 0 | — | Chinese invoice |
| G26 | zh | genuine | SAFE | 0 | — | Chinese reminder |
| G27 | zh | genuine | SAFE | 0 | — | Chinese anti-scam notice (trap) |
| G28 | zh | genuine | SAFE | 0 | — | Chinese instalment |
| G29 | en | genuine | SAFE | 0 | — | Bilingual EN/MS |
| G30 | en | genuine | SAFE | 0 | — | US deposit (low but valid) |
| S01 | en | scam | BLOCK | 100 | lookalike_domain, bank_mismatch, urgency, threat, unusual_method | look-alike payments domain + new bank + crypto |
| S02 | en | scam | BLOCK | 80 | lookalike_domain, bank_mismatch | typo-squat domain + changed bank |
| S03 | en | scam | REVIEW | 35 | lookalike_domain | Cyrillic look-alike domain |
| S04 | en | scam | BLOCK | 70 | unofficial_domain, bank_mismatch | gmail sender + changed bank |
| S05 | en | scam | REVIEW | 45 | bank_mismatch | spoofed official sender, only bank changed |
| S06 | en | scam | BLOCK | 65 | lookalike_domain, unusual_method | gift cards |
| S07 | en | scam | BLOCK | 100 | lookalike_domain, bank_mismatch, urgency, unusual_method | personal account of 'bursar' |
| S08 | en | scam | BLOCK | 60 | lookalike_domain, urgency, amount_anomaly | absurd amount |
| S09 | en | scam | BLOCK | 95 | lookalike_domain, bank_mismatch, currency_mismatch | wrong currency + look-alike |
| S10 | en | scam | REVIEW | 50 | unknown_payee, urgency | unknown institution name |
| S11 | en | scam | REVIEW | 50 | urgency, prompt_injection, hidden_content | hidden AI instructions only (official look) |
| S12 | en | scam | REVIEW | 55 | bank_mismatch, hidden_content | zero-width hidden text + changed bank |
| S13 | en | scam | BLOCK | 75 | lookalike_domain, threat, unusual_method | visa threat + Western Union |
| S14 | en | scam | REVIEW | 55 | bank_mismatch, reference_mismatch | reference mismatch + new bank |
| S15 | en | scam | BLOCK | 65 | lookalike_domain, prompt_injection | fake system message |
| S16 | ms | scam | BLOCK | 100 | lookalike_domain, bank_mismatch, urgency, unusual_method | Malay crypto + look-alike |
| S17 | ms | scam | BLOCK | 100 | unofficial_domain, bank_mismatch, threat, unusual_method | Malay cancellation threat + personal account |
| S18 | ms | scam | REVIEW | 40 | urgency, prompt_injection | Malay injection |
| S19 | ms | scam | REVIEW | 45 | bank_mismatch | Malay changed bank only (spoofed sender) |
| S20 | bn | scam | BLOCK | 90 | unofficial_domain, bank_mismatch, urgency, threat | Bangla visa threat + bKash personal |
| S21 | bn | scam | BLOCK | 75 | lookalike_domain, urgency, unusual_method | Bangla crypto |
| S22 | bn | scam | REVIEW | 40 | urgency, prompt_injection | Bangla agent injection |
| S23 | bn | scam | BLOCK | 100 | unofficial_domain, bank_mismatch, unusual_method | Bangla hundi agent |
| S24 | zh | scam | BLOCK | 100 | lookalike_domain, bank_mismatch, urgency, threat, unusual_method | Chinese urgency + cancel enrolment + personal account |
| S25 | zh | scam | BLOCK | 65 | lookalike_domain, unusual_method | Chinese bitcoin |
| S26 | zh | scam | REVIEW | 40 | urgency, prompt_injection | Chinese agent injection |
| S27 | zh | scam | REVIEW | 45 | bank_mismatch | Chinese changed bank only (spoofed sender) |
| S28 | en | scam | BLOCK | 90 | lookalike_domain, bank_mismatch, urgency | deposit scam to new student, look-alike AU |
| S29 | en | scam | BLOCK | 80 | lookalike_domain, unusual_method, amount_anomaly | fake refund requiring fee |
| S30 | en | scam | REVIEW | 45 | lookalike_domain, hidden_content | encoded blob + look-alike |
