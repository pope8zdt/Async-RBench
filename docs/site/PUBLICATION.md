# Public website

`published/` is the editable source snapshot for the public website. It contains
the current single-page layout, dynamic cover, six illustrated trajectory cases
and the bilingual evaluation guide. Earlier generators remain available for
data and layout development; they are not the Pages deployment source.

The snapshot uses root-relative links. `publication.py` validates it and adds
the GitHub project prefix when building, including JavaScript-generated URLs.

```sh
python -m unittest discover -s docs/site/publication-tests -p 'test_*.py'
node --test docs/site/publication-tests/publication.test.mjs
python docs/site/publication.py --output dist/site --base-path /Async-RBench
```

Use a new or empty output directory. To preview the built project URL, serve its
parent and place the output at `preview/Async-RBench`, then open
`http://127.0.0.1:8000/Async-RBench/`. The build performs no API calls or evaluation.

## Data boundary

- Paper leaderboard data, the corpus, configuration template, PDF and experiment
  figures are protected by `publication-integrity.json`. Update those hashes only
  when deliberately updating the corresponding scientific source.
  The local `.gitattributes` also disables line-ending conversion for these files.
- `data/trajectories.public.json` contains selected, previously displayed event
  fields from six archived runs. It is not a complete trace or a new evaluation.
  Source hashes and original sequence numbers retain provenance. Model messages,
  hidden judges, local source paths, credentials and local trial outputs are not
  included. Descriptions distinguish observations from interpretations.
- No `.local.json` bundles or raw `.jsonl` logs are accepted by the release check.
  Adding a case requires review of its fields and an explicit record allowlist.
- Model names, paper numbers, task names and English diagrams are not editorial
  copy. Preserve them when changing page prose or presentation.

## Editing

Edit the snapshot's HTML, CSS and modules directly. Keep diagrams in English;
Chinese and English interface text lives in paired language spans or module
labels. Preserve pause controls, reduced-motion styles, keyboard access and
the complete setup commands. After editing, run both test suites and inspect
desktop and mobile views before publishing. Pages deploys only after validation.

The October 2026 editorial pass replaced question-led promotional copy with a
direct statement of the research task, clarified section labels, removed local
preview notices and softened background contrast. Original illustrations,
paper data and movement remain intact.
