from __future__ import annotations

from collections import defaultdict

from backend.app.semantic.descriptor import semantic_text
from backend.app.semantic.embeddings import EmbeddingProviderError

from .core import search, snapshot_id
from .models import Bundle, Entry, Space
from .store import ExplorerStore


class ExplorerService:
    def __init__(self, repository, store: ExplorerStore):
        self.repository = repository
        self.store = store

    def library(self) -> tuple[dict[str, Bundle], dict[str, int]]:
        groups = defaultdict(list)
        spaces = {}
        excluded = {"no_embedding": 0, "stale_revision": 0, "invalid_embedding": 0}
        for item in self.repository.get_library_items():
            try:
                if (
                    self.repository.get_run(item.run_id).result_revision
                    != item.result_revision
                ):
                    excluded["stale_revision"] += 1
                    continue
                if item.embedding is None:
                    excluded["no_embedding"] += 1
                    continue
                embedding = item.embedding
                space = Space(
                    provider=embedding.provider,
                    model=embedding.model,
                    revision="provider-managed",
                    dimensions=embedding.dimensions,
                    mode="text",
                    preprocessing="semantic_text-v1",
                    descriptor_version=embedding.descriptor_version,
                )
                vector = self.repository.get_embedding(
                    embedding.cache_key,
                    embedding.model,
                    embedding.dimensions,
                    embedding.descriptor_version,
                )
                attributes = item.descriptor.dimensions.model_dump()
                attributes.update(
                    {
                        k: getattr(item.descriptor, k, None)
                        for k in ("material", "finish", "structure")
                    }
                )
                entry = Entry(
                    id=item.id,
                    label=item.label,
                    vector=vector,
                    text=semantic_text(item.descriptor),
                    run_id=item.run_id,
                    result_revision=item.result_revision,
                    attributes=attributes,
                    category=item.descriptor.family,
                    category_origin="reviewed"
                    if getattr(item.descriptor, "classification_status", "hypothesis")
                    == "confirmed"
                    else "unknown",
                )
                entry = entry.model_copy(
                    update={"content_hash": item.descriptor_fingerprint}
                )
                key = "library:" + space.id
                groups[key].append(entry)
                spaces[key] = space
            except (KeyError, ValueError, EmbeddingProviderError):
                excluded["invalid_embedding"] += 1
        return {
            key: Bundle(
                space=spaces[key],
                entries=tuple(sorted(entries, key=lambda e: e.id)),
                provenance="Biblioteca de la instancia; revisiones vigentes; embeddings persistidos del proveedor",
            )
            for key, entries in groups.items()
        }, excluded

    def list_spaces(self) -> dict:
        library, excluded = self.library()
        result = [
            {
                "id": key,
                "count": len(b.entries),
                "space": b.space.model_dump(),
                "source": "library",
            }
            for key, b in library.items()
        ]
        errors = []
        for catalog in self.store.catalogs():
            try:
                release, bundle = self.store.load(catalog)
                result.append(
                    {
                        "id": "corpus:" + catalog,
                        "count": len(bundle.entries),
                        "space": bundle.space.model_dump(),
                        "source": "corpus",
                        "release_id": release,
                    }
                )
            except (ValueError, KeyError):
                errors.append({"catalog": catalog, "code": "corrupt_release"})
        return {
            "spaces": sorted(result, key=lambda s: s["id"]),
            "excluded": excluded,
            "errors": errors,
            "catalog_scope": "shared_authenticated_instance",
        }

    def load(self, source: str) -> tuple[Bundle, str]:
        if source.startswith("corpus:"):
            release, bundle = self.store.load(source.removeprefix("corpus:"))
            return bundle, f"{source}:{release}"
        bundle = self.library()[0].get(source)
        if bundle is None:
            raise KeyError(source)
        return bundle, source

    def snapshot(self, source: str) -> dict:
        bundle, identity = self.load(source)
        result = self.store.snapshot(bundle, identity)
        self.checked(source, result["snapshot_id"])
        return result | {"space_key": source}

    def checked(self, source: str, expected: str) -> Bundle:
        bundle, identity = self.load(source)
        if snapshot_id(bundle, identity) != expected:
            raise ValueError("stale_snapshot")
        return bundle

    def search(self, request) -> dict:
        bundle = self.checked(request.space, request.snapshot_id)
        results = search(
            bundle,
            request.member_id,
            request.limit,
            request.category,
            request.exclude_group,
        )
        self.checked(request.space, request.snapshot_id)
        return {
            "snapshot_id": request.snapshot_id,
            "neighbors": results,
            "method": "exact_cosine_original_dimensions",
        }
