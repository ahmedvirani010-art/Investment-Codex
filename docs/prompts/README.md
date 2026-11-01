# Investment Codex prompt catalogue

Start with [the PDF catalogue](Investment_Codex_Prompt_Catalogue.pdf) or
[34 copyable prompts](Investment_Codex_Prompts.md). Every prompt lists the inputs,
execution route, native output formats and state changes. JSON templates contain
labelled placeholders and must be filled with current dataset/run identities.

The guide documents implemented capabilities and the dated operational limits;
it does not activate production or certify real financial data. The application
produces Excel/JSON/Markdown. PDF generation here is a separate documentation step.

`prompt-catalogue.json` contains the structured prompts; `input-contracts.json`
records the inspected schema fields. Refresh those against the application before
using this guide after schema changes. The ZIP groups the user-facing deliverables.

## Rebuild documentation

Use a separate Python environment and install `requirements.txt`, then run:

```sh
python docs/prompts/build_catalogue.py
```

The builder writes beside itself and uses system Open Sans when available,
otherwise Helvetica. ReportLab is a documentation dependency only; it is not
added to the calculation runtime or its lock file. The fixed review dates and
schema inventory need explicit review when refreshing this catalogue.
