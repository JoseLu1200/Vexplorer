# Public furniture production benchmark

Retrieval date: 2026-11-14.

This directory contains a small, public, source-preserving benchmark derived from:

- Grotowska, M.; Grzegorzewska, E.; Beer, P.; Oleńska, S. (2026), "Creative Upcycling of Wood Waste into Furniture: Bridging Durability Testing and Economic Viability, a Case Study", *Sustainability* 18(15), 7720. DOI: https://doi.org/10.3390/su18157720
- Publication date: 2026-07-30.
- License: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/

Files:

- `source_sustainability-18-07720.pdf` and `.xml`: unmodified publisher downloads.
- `production_budget.csv`: four published production-budget rows, with dimensions and material use where the article reports them.
- `retail_benchmark.csv`: sales/revenue figures kept separate from production costs.
- `historical_import.json`: conservative mapping to Vexplorer's `HistoricalImport` schema.
- `manifest.json`: provenance, scope and SHA-256 checksums.

Important limitations:

- The paper calls these figures an assumed/preliminary economic analysis. They are imported with `cost_basis: budget`, not as closed ERP actuals.
- `origin: published` identifies this academic benchmark distinctly from executed company history (`actual`) and fixtures (`synthetic`).
- The explicit scopes are `cost_scope: [material, labor, indirect]`, `hours_scope: [labor]`, and their union in `included_scope`.
- Retail/net-sales values are not placed in the Vexplorer production-cost field.
- The square table's outer dimensions are not stated in the text/table and remain absent.
- The pouf source is internally inconsistent: Table 2 lists six 440 x 440 x 18 mm boards, while the narrative describes a 380 x 380 x 18 mm board. The normalized import uses Table 2 and records the conflict in provenance notes.
- This is a four-product academic case study of upcycled furniture, not a representative factory history and not a benchmark for all furniture families.

Attribution is required for redistribution or adaptation under CC BY 4.0.
