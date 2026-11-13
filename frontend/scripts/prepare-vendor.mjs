import { cp, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const files = [
  ["node_modules/three/build/three.module.js", "vendor/three/three.module.js"],
  ["node_modules/three/build/three.core.js", "vendor/three/three.core.js"],
  ["node_modules/three/examples/jsm/controls/OrbitControls.js", "vendor/three/addons/controls/OrbitControls.js"],
  ["node_modules/three/LICENSE", "vendor/three/LICENSE"],
];

for (const [source, target] of files) {
  const destination = resolve(root, target);
  await mkdir(dirname(destination), { recursive: true });
  await cp(resolve(root, source), destination);
}

console.log("Three.js local preparado en frontend/vendor/three");
