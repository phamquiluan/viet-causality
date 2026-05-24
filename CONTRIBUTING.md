# Contributing

Thanks for helping grow this list. There are three ways to contribute.

## 1. Add a researcher (or yourself)

Open a pull request that adds an entry to [`_data/researchers.yml`](_data/researchers.yml) following the schema below.

```yaml
- id: nguyen-anh-example          # unique kebab-case slug
  name: "Nguyen, Anh Example"      # "Family, Given" in ASCII
  name_vi: "Nguyễn Anh Ví Dụ"      # optional, with diacritics
  affiliation:
    institution: "Example University"
    country: "United States"
    position: "Assistant Professor"   # see allowed values below
  links:
    homepage: "https://example.edu/~aen"
    scholar:  "https://scholar.google.com/citations?user=XXXXXXX"
    dblp:     "https://dblp.org/pid/XXX/YYY.html"
    orcid:    "0000-0000-0000-0000"
    github:   "https://github.com/anhnguyen"
  sub_areas: [causal-discovery, causal-ml]   # see allowed values below
  key_papers:
    - title:  "Causal Inference for X"
      venue:  "NeurIPS"
      year:   2024
      url:    "https://arxiv.org/abs/XXXX.XXXXX"
  alumnus_of:
    - "VNU University of Science"
    - "VinAI Research"
  notes: "Focus on causal representation learning for healthcare."
  source: manual_seed                # see allowed values below
  confidence: high                   # high | medium | low
  last_verified: 2026-05-24
```

### Allowed `position` values

`Full Professor`, `Associate Professor`, `Assistant Professor`, `Senior Lecturer`, `Lecturer`, `Senior Research Scientist`, `Research Scientist`, `Research Fellow`, `Postdoc`, `PhD Student`, `Industry Researcher`, `Emeritus Professor`, `Other`.

### Allowed `sub_areas` values

`theoretical` (SCMs, do-calculus, identifiability), `causal-discovery`, `causal-ml` (treatment effects with neural nets, causal representation learning), `causal-rl`, `applied-health`, `applied-econ`, `applied-social`, `applied-bio`, `counterfactual-fairness`, `counterfactual-explanation`, `causal-nlp`, `causal-cv`, `causal-time-series`.

### Allowed `source` values

`manual_seed`, `self_submitted`, `community_pr`, `scrape_openalex`, `scrape_semantic_scholar`, `scrape_dblp`, `scrape_arxiv`, `referral`.

## 2. Correct or remove an entry

Open an issue using the `correction` or `opt-out` label, or directly edit the YAML in a PR. Removal requests are honored without discussion.

## 3. Improve the methodology

The scripts under `scripts/` pull candidates from OpenAlex, Semantic Scholar, DBLP, and arXiv. Improvements to disambiguation logic, new data sources, or scheduled refresh actions are welcome.

## Ethics

This list relies on a mix of self-identification and inference from names + affiliations. We label each entry's `confidence` and `source` so readers can judge. If you do not want to be listed, open an `opt-out` issue and we will remove the entry the same day.
