# Agente PR2 — restauración tras integración upstream

## Identidad y alcance

- Agente de IA delegado para restaurar selectivamente las correcciones PR2 perdidas al integrar `main`.
- Único escritor de backend, herramientas y pruebas PR2 durante este bloque, excepto `extraction.py` y `test_dxf_ingest_hardening.py`.
- Sin commit, push ni despliegue; coordinación central conserva esas acciones.

## Objetivo

Recuperar sobre el árbol integrado los fixes verificados de calibración, precedentes, mantenimiento de embeddings, similitud numérica y pandeo, preservando recuperación durable y el agrupamiento posterior por enlace completo.

## Decisiones de integración

- Restaurar módulos completos solo cuando el delta desde `cb6b410` corresponde exclusivamente a la pérdida PR2.
- Aplicar parches quirúrgicos en `main.py` y `repository.py` para conservar checkpoints y recuperación de trabajos.
- Mantener `similarity/service.py` y `clustering.py` del árbol más reciente; comprobar por prueba el mínimo entre pares.
- No tocar los archivos CAD reservados a otro agente.

## Verificación

- Suite focal inicial tras recomponer producción: 79 aprobadas; reveló únicamente expectativas antiguas de pandeo/calibrador y que la política de publicación seguía ligada por error a `public_production`.
- Se restauró la política en toda producción (`environment == "production"`) sin bloquear desarrollo local ni cambiar el acceso público previsto.
- Suite focal final ampliada: 87 aprobadas, 1 aviso deprecado de `TestClient`, 11,99 s.
- Coordinación confirmó además 17 aprobadas frescas para calibrador, publicación y pandeo, cubriendo los seis fallos que la primera suite global había cargado antes de la corrección.
- Auditoría posterior confirmó que faltaban tests PR2 aunque el código ya estaba restaurado. Se recuperaron todos los `test_*` presentes en `cb6b410`: export runtime/CLI del calibrador, explicación de pandeo, rotación/invalidation/concurrencia, asociación explícita de apoyos y catálogo provisional.
- Política de publicación reconciliada con el avance legítimo de `main`: la atestación obligatoria corresponde a producción pública (`public_production`), no a la biblioteca privada autenticada. Se revirtió la interpretación inicial más amplia y se conservaron las pruebas nuevas de acceso privado y denylist LF/CRLF.
- Focal exhaustiva final de todo el mapa PR2 más publicación/acceso: 128 aprobadas, 1 aviso deprecado, 25,58 s.
- `git diff --check`: sin errores.

## Cierre

- Producción congelada después de la verificación focal.
- Sin commits ni push.
- Suite global final repetida por coordinación sobre el árbol congelado.
