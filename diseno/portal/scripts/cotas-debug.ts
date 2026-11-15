// Lista las cotas calculadas de un caso: node scripts/probar-general.mjs no la cubre. Uso: ver scripts/cotas-debug.mjs
import { cargarCaso } from "../src/casos";
import { cotasCalculadas } from "../src/general/cotas";
import type { CasoId } from "../src/casos";

for (const id of (process.argv[2] ?? "plank_030").split(",") as CasoId[]) {
  const mesa = await cargarCaso(id);
  const cotas = mesa.plano ? cotasCalculadas(mesa.plano) : [];
  console.log(`${id}: ${cotas.length} cotas`);
  for (const p of mesa.piezas) if (p.confianza) console.log(`  [${p.confianza.nivel}] ${p.id}: ${p.confianza.motivo.slice(0, 110)}`);
  for (const c of cotas) console.log(`  ${c.id.padEnd(22)} ${c.texto.padStart(5)}  texto en ${c.posicionTexto.map((v) => Math.round(v)).join(", ")}`);
}
