# Fabrication Attribution

Codex offline attribution of the judge's `no_fabricated_facts` failures. Original scores remain unchanged. The categories classify the nature of each reported failure and are not a claim of independent human calibration.

| Batch / answer | Attribution | Review |
| --- | --- | --- |
| Bazi-single `bazi_pilot_trait#1` | 叙述类 | Presents personal habits and relationship tendencies as known behavior, including being deferential, over-preparing, and giving friends money. These are not established by chart facts. |
| Bazi-single `bazi_pilot_next_month_career#1` | 叙述类 | The judge's specific arithmetic and cycle concern does not match the calculated facts: element counts are 木2火1土2金3水0, and 丁亥 is the sole current cycle for the as-of date. Under review §7, judge misreads are attributed to narrative class; original failure remains. |
| Bazi-single `bazi_pilot_trait#3` | 叙述类 | The judge returned no explanation. The answer itself asserts unverified personal routines, self-criticism, and relationship patterns as if known. Per §7, the empty judge explanation is retained without rescoring. |
| Bazi-pipeline `bazi_pilot_investment_risk#1` | 事实类 | The answer uses date-only boundaries for the year change and labels 2027-02-04 as the 立春 boundary without the computed 09:46 Beijing time. The distinction affects which part of that date belongs to each flow year. |
| Bazi-pipeline `bazi_pilot_typed_birth#2` | 叙述类 | The answer turns symbolic relations into likely concrete relationship events and partner traits (for example, renewed contact or a strong-willed partner), which are not known user experiences. |

The complete machine input used for the counts is [fabrication-reviewed.yaml](fabrication-reviewed.yaml); the resulting denominator and counts are in [fabrication-counts.md](fabrication-counts.md).
