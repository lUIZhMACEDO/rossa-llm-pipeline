# ROSSA entry review: doyard_2016  (source: manual)

Draft produced by the pipeline. Nothing here is submitted anywhere; a person checks every row.

## Study Information (step 2a: title and summary)

| Field | Suggested value | Confidence | Quote check |
|---|---|---|---|
| title | Decreased Bone Formation Explains Osteoporosis in a Genetic Mouse Model of Hemo… | high | verified in paper |
| summary | Osteoporosis may complicate iron-overload diseases such as genetic hemochromato… | high | verified in paper |
| funding | This work was supported by grants from Region Bretagne (MD) and the "Societe Fr… | high | verified in paper |
| conflicts_of_interest | The authors have declared that no competing interests exist. | high | verified in paper |
| study_completion_date | 2016-02-01 | low | verified in paper |
| has_been_published | yes | high | verified in paper |
| doi | 10.1371/journal.pone.0148292 | high | verified in paper |
| pubmed_id | - | not_found | n/a |

Reviewer flags from the model:

- The title ends in 'Hemochromatosiss' (double s) - copied exactly as printed; looks like a typo in the original.
- study_completion_date: the article gives no explicit study end date, so the publication date (2016-02-01) was used as a stand-in. Confirm or replace.
- pubmed_id: not present in the article text. It can be looked up on PubMed (the study's PubMed ID is 26829642) and added by a human - not filled here because it is not in the source.
- Accented characters were simplified to ASCII in the values (Region, Societe, Francaise); confirm preferred spelling.

Produced by: "unspecified"

## Investigators (step 2b: investigator info)

| Field | Suggested value | Confidence | Quote check |
|---|---|---|---|
| investigators[0].role | corresponding | medium | verified in paper |
| investigators[0].first_name | Pascal | high | verified in paper |
| investigators[0].last_name | Guggenbuhl | high | verified in paper |
| investigators[0].email | pascal.guggenbuhl@chu-rennes.fr | high | verified in paper |
| investigators[0].department | Service de Rhumatologie (Rheumatology) | medium | verified in paper |
| investigators[0].organization | Universite de Rennes 1 / CHU Hopital Sud, Rennes | medium | verified in paper |
| investigators[0].country | France | high | verified in paper |

Reviewer flags from the model:

- A SUBMITTING investigator is required by ROSSA but cannot come from the paper (the depositor is not named in the article). A human must add one (likely the ROSSA account holder).
- Only the corresponding author (Pascal Guggenbuhl) was entered. The other authors - Mathilde Doyard, Daniel Chappard, Patricia Leroyer, Marie-Paule Roth, Olivier Loreal - can be added as 'contributing' if ROSSA wants the full author list.
- Guggenbuhl's role was inferred from the asterisk + email line, not an explicit 'corresponding author' statement.
- Affiliation was split into department/organization/country by mapping superscripts 1, 2 and 6; the organization combines a university and a hospital affiliation. Confirm the intended split for ROSSA.

Produced by: "unspecified"

## Animal Experimentation (step 2c: animal experimentations)

| Field | Suggested value | Confidence | Quote check |
|---|---|---|---|
| setup.genetic | true | high | verified in paper |
| setup.drug | false | high | n/a |
| setup.gonadectomy | false | high | n/a |
| animal_models[0].species | Mouse | high | verified in paper |
| animal_models[0].animal_strain | C57BL/6 | high | verified in paper |
| animal_models[0].genetic_modification_category | Global Knockout/Knockin - Gene Targeting | medium | verified in paper |
| animal_models[0].animal_model_name | - | not_found | n/a |
| animal_models[0].genetic_method | Knockout (KO) | high | verified in paper |
| animal_models[0].functional_change | Loss of Function | medium | verified in paper |
| animal_models[0].modified_gene | Hfe | high | verified in paper |
| animal_models[0].modified_gene_species | Mouse | medium | verified in paper |
| animal_models[1].species | Mouse | high | verified in paper |
| animal_models[1].animal_strain | C57BL/6 | high | verified in paper |
| animal_models[1].genetic_modification_category | No Genetic Modification | high | verified in paper |
| animal_models[1].animal_model_name | - | not_found | n/a |
| animal_models[1].genetic_method | - | not_found | n/a |
| animal_models[1].functional_change | - | not_found | n/a |
| animal_models[1].modified_gene | - | not_found | n/a |
| animal_models[1].modified_gene_species | - | not_found | n/a |

Reviewer flags from the model:

- Calcein (10 mg/kg, 7 and 2 days before euthanasia) was a bone-mineralization LABEL, not an experimental drug - excluded from drug_treatments per ROSSA guidance.
- Xylazine/Ketamine (Rompun/Imalgene) was anaesthesia before euthanasia - excluded from drug_treatments.
- genetic_modification_category 'Global Knockout/Knockin - Gene Targeting' was inferred from 'Hfe-/-'; the paper does not state the exact targeting method. Confirm against the real ROSSA categories.
- functional_change 'Loss of Function' is the standard interpretation of an Hfe knockout but is not stated verbatim in the paper.
- Sex, age and sample size (n=7 per group) are intentionally NOT recorded here - on the real ROSSA form they belong under Phenotype Analysis > Sample Groups, which is outside this assignment's three sections.

Produced by: "unspecified"

## Summary

- 34 fields checked, 27 filled, 7 left empty (not found).
- 25 values have a quote that was found verbatim in the paper.
- 0 values have a missing or unfindable quote (confidence forced to low).
