/** Tonos de material por confianza (Construcción 3D): madera clara, arena y terracota, apagados y distinguibles. */
export const COLOR_CONFIANZA = { alta: "#e2c799", media: "#b3a68a", baja: "#b8664b" } as const;
export type NivelConfianza = keyof typeof COLOR_CONFIANZA;
