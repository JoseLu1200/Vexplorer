import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { formatSimilarityScore, libraryCounts, libraryEmptyMessage, presentPieceDifferences, similarityScoreLabel } from "../core/similarity-ui.js";
import { presentLibraryDifferences } from "../core/ui.js";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const helper = await readFile(new URL("../core/similarity-ui.js", import.meta.url), "utf8");

test("cosine similarity keeps meaningful precision and explicitly denies identity", () => {
  const label=formatSimilarityScore(0.999546,"en-US");
  assert.equal(label,"99.9546 % (0.999546); no implica identidad");
  assert.doesNotMatch(label,/100|idéntic/i);
  assert.match(app, /formatSimilarityScore/);
  assert.doesNotMatch(app, /item\.score\.toFixed\(3\)/);
  assert.match(helper, /no implica identidad/i);
});

test("raw score names the metric actually used", () => {
  assert.match(similarityScoreLabel({score:0.8,score_kind:"geometric_similarity"},"geometric"),/^similitud geométrica/);
  assert.match(similarityScoreLabel({score:0.8,score_kind:"cosine_similarity"},"semantic"),/^similitud coseno/);
});

test("library results distinguish typology, technical comparison and unverified production fields", () => {
  assert.match(app, /Coincidencia tipológica/);
  assert.match(app, /Comparación técnica/);
  assert.match(app, /material, acabado ni proceso de fabricación/i);
  assert.match(app, /candidate\?\.descriptor\?\.family/);
  assert.match(app, /material_tariff_id_unknown:"Material o tarifa sin confirmar"/);
  assert.match(app, /process_unknown:"Proceso de fabricación sin confirmar"/);
  assert.match(app, /technical_fields_unknown:"Datos técnicos incompletos"/);
  assert.match(app, /item\.member_ids=item\.member_ids\?\?item\.equivalent_record_ids/);
});

test("library summary separates unique designs, stored records and duplicates", () => {
  assert.deepEqual(libraryCounts({design_count:2,record_count:5,duplicate_record_count:3},[{},{},{}]),{designs:2,records:5,duplicates:3});
  assert.match(helper, /design_count/);
  assert.match(helper, /record_count/);
  assert.match(helper, /duplicate_record_count/);
  assert.match(app, /include_summary:true/);
});

test("empty library and unavailable provider are rendered as separate states", () => {
  assert.match(libraryEmptyMessage(0),/mobiliario real/);
  assert.match(libraryEmptyMessage(0),/fixtures de demo no se publican/i);
  assert.match(html, /id="library-status"/);
  assert.match(html, /id="provider-status"/);
  assert.match(helper, /Biblioteca pública vacía/);
  assert.match(app, /Proveedor semántico/);
});

test("piece differences expose multiplier and optional side-by-side thumbnails", () => {
  assert.deepEqual(presentPieceDifferences([{field:"components.lateral.thickness_mm",query_value:18,candidate_value:36}]),[{label:"lateral",fieldLabel:"Grosor",summary:"18 ↔ 36 mm",ratioLabel:"×2"}]);
  assert.deepEqual(presentPieceDifferences([{field:"part_features[0].width_mm",query_value:null,candidate_value:300}])[0],{label:"Pieza 1",fieldLabel:"Ancho",summary:"desconocido ↔ 300 mm",ratioLabel:""});
  assert.equal(presentPieceDifferences([{field:"components.side.width_mm",label:"<img onerror=alert(1)>"}])[0].label,"<img onerror=alert(1)>");
  assert.match(helper, /thickness_mm/);
  assert.match(helper, /ratioLabel/);
  assert.match(app, /comparison-thumbnails/);
  assert.match(app, /api\.getRun/);
  assert.match(app, /api\.documentPreviewUrl/);
  assert.doesNotMatch(app, /current_thumbnail_url/);
  const compact=presentLibraryDifferences([{field:"components.side_support[0].length_mm",query_value:720,candidate_value:728}]);
  assert.deepEqual(compact.summary,["Datos técnicos de comparación disponibles"]);
  assert.match(compact.technical[0],/components\.side_support\[0\]\.length_mm/);
  assert.equal(presentPieceDifferences([{field:"components.side_support[0].length_mm",query_value:720,candidate_value:728}])[0].label,"Soporte lateral1");
  assert.equal(presentPieceDifferences([{field:"components.tabletop[0].width_mm",query_value:720,candidate_value:728}])[0].label,"Tapa1");
});

test("production publication requires an explicit real reviewed attestation", () => {
  assert.match(html,/id="library-source-reference"/);
  assert.match(html,/id="library-public-approved"/);
  assert.match(app,/library_requires_real_reviewed/);
  assert.match(app,/source_kind:"real_furniture"/);
  assert.match(app,/approved_for_public_library:true/);
  assert.match(html,/data-panel-content="library"[\s\S]*?id="library-publication"/);
});

test("grouping controls name their criterion and offer useful presets", () => {
  assert.match(app, /updateGroupingLabels/);
  assert.match(html, /Similitud geométrica mínima/);
  assert.match(html, /Enlace completo: todos los pares/);
  assert.match(html, /data-threshold-preset="0\.70"/);
  assert.match(html, /data-threshold-preset="0\.85"/);
  assert.match(html, /data-threshold-preset="0\.95"/);
});

test("boot resolves library and provider status before any run is selected", () => {
  assert.match(app, /async function refreshInitialLibrary\(\)/);
  assert.match(app, /await api\.getLibrary\(\)/);
  assert.match(app, /renderLibraryEntries\(library\)/);
  assert.match(app, /Biblioteca no disponible:/);
  assert.match(app, /configureModes\(await api\.getConfig\(\)\)[\s\S]*await refreshInitialLibrary\(\)/);
});

test("public status separates configured provider, empty index and private generation", () => {
  assert.match(app, /Proveedor semántico configurado/);
  assert.match(app, /registros indexados/);
  assert.match(app, /búsqueda semántica no disponible/);
  assert.match(app, /Generar embeddings requiere autenticación/);
  assert.match(app, /toggleHidden\(\$\("#history-list"\),!state\.features\.history\)/);
  assert.match(app, /toggleHidden\(estimateTab,!state\.features\.costs\)/);
  assert.match(app, /toggleHidden\(estimatePanel,!state\.features\.costs\)/);
});

test("cached semantic search remains available without a configured generation provider", () => {
  assert.match(app, /providerConfigured=Boolean\(semantic\.provider_configured\|\|semantic\.available\)/);
  assert.match(app, /searchAvailable=Boolean\(semantic\.cached_search_available\|\|semantic\.available\)/);
  assert.match(app, /Number\.isInteger\(rawDimensions\)\?`\$\{rawDimensions\} dimensiones`/);
});


