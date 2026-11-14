# Published furniture production-time benchmark

Retrieval date: 2026-11-14.

Source:

- Nuriyev, A.; Gardashova, L.; Aghajanova, G.; Yusufov, R.; Sardarli, N. (2026), "Sustainable Production Planning Under Uncertainty: A Z-Number-Based Multi-Objective Optimization Approach for Furniture Manufacturing", *Sustainability* 18(18), 9636.
- DOI: https://doi.org/10.3390/su18189636
- Publication date: 2026-09-20.
- License: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/

The article validates its model on real monthly production data from three anonymized furniture enterprises in Azerbaijan. Tables 1-3 and A2/A4/A6 publish per-unit production-time coefficients for 15 named products across bedroom, children's and living-room furniture.

Files:

- `source_sustainability-18-09636.pdf` and `.xml`: unmodified publisher downloads.
- `published_hours.csv`: the 15 published central, lower and upper time coefficients plus reliability values.
- `historical_import.json`: Vexplorer import containing only central production-time hours.
- `manifest.json`: source, scope and checksums.

Limitations:

- These are published model coefficients derived from monthly enterprise data, not timestamped closed work orders and not a labor-hour breakdown.
- The central coefficient is stored in `manufacturing_hours`; lower/upper Z-number values and reliability remain in CSV and provenance notes, not as invented statistical intervals.
- Product-level dimensions, material and finish are not published and remain absent.
- Profit and resource figures in the article are not imported as cost, price, material consumption or dimensions.
- `quantity: 1` represents the paper's explicit per-unit coefficient, not a disclosed historical batch size.
- The article says additional/raw data are available only on request. No restricted or contractual data were requested or downloaded.

Attribution is required for redistribution or adaptation under CC BY 4.0.
