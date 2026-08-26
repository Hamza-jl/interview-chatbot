# Templates

The two Word files this application fills are **not** in the repository. They
belong to the organisation being interviewed, and the question plan is derived
one-to-one from their tables, so a substitute will not simply drop in.

Place your own here:

```
backend/templates/
├── etat_des_lieux_dsi.docx      # IT-department questionnaire
└── etat_des_lieux_entite.docx   # business-unit questionnaire
```

Filenames are configured in `app/pca/blueprint.py` (`TEMPLATE_FILES`).

## Making the plan match your templates

Every question in `blueprint.py` carries the exact coordinates of the cell or
table it writes to:

```python
Question(
    id="dsi.fiche.responsable",
    kind="field",
    target=Target(table=1, row=2, col=1, mode="cell"),
    ...
)
```

`table` is 1-based in document order; `row` and `col` are 0-based within it.
Grid questions use `mode="rows"` and must declare exactly as many `Column`
entries as the target table has columns.

Two tests keep the plan honest and will tell you precisely what is wrong:

```bash
python -m pytest tests/test_interview.py -k "targets_a_real_table or same_cell"
```

They fail with the offending question id and the mismatch, so adapting the plan
to a new pair of templates is a matter of following the errors until they pass.
Without the files present, every test that opens a template is skipped.
