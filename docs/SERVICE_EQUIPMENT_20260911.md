# Service equipment presentation — 11 September 2026

The user-supplied `Ibtikar canvas PLAGENOR-ESSBO VF 2025.ods` contains 40 equipment entries and 11 historical services. Its photo fields are empty and no image objects are embedded. The current eight-service registry remains authoritative for active services, prices and service scope. No historical prices, availability or contact details were imported.

All eight active services now have associated equipment and explanatory scope notes in French, English and Arabic. These appear as presentation metadata, separate from stored financial and administrator-managed service data. Existing uploaded photographs take precedence on the homepage, catalogue, detail and request landing pages. New services can use the existing image-upload control; an admin preview is included. Failed images retain a neutral fallback and the equipment name.

## External illustrative photographs

- Illumina MiSeq: Konrad Förstner, CC0 1.0 public-domain dedication. https://commons.wikimedia.org/wiki/File:Illumina_MiSeq_sequencer.jpg
- PCR thermal cycler: Tinojasontran, released into the public domain. https://commons.wikimedia.org/wiki/File:PCR_machine.jpg

Both are explicitly illustrative photographs taken outside PLAGENOR. The PCR photo shows a Bio-Rad model, not a confirmed model from ESSBO. Source links appear on the detail/request pages. Images load from the explicitly allowed `thumb.wikimedia.org` host with no referrer. They remain externally hosted because the local download attempt was blocked by network approval cancellation. The browser regression test substitutes a local fixture for deterministic layout and failure testing; it does not certify external CDN availability.

Actual photographs are still needed for MALDI Biotyper, MerMade 4, Beta 2-8 LSCplus, the nucleic-acid QC equipment and the Sanger analyzer (used by two services). Manufacturer-owned photographs and photos of mismatched sequencer models were not substituted.

## Validation

See the associated PR for CI results. Regression tests cover all locales, all eight mappings, uploaded-photo precedence, unknown future services, source disclosure, responsive layout and image failures. No migration or pricing change is required.
