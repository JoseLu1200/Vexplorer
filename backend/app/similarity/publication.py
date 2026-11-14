from __future__ import annotations

from backend.app.contratos.modelos import DrawingExtraction, Result


KNOWN_BUNDLED_FIXTURE_SHA256 = frozenset({
    "05f8da7e68a1fd3411ee4491cb3aa341c6221e7869727ee49f60d3f90bc83994",
    "10276ed3482aee6629964da0ecab6329cdce4d913a42c6b33ee3963a45a38d3e",
    "4c3859050cfb54e18b27baf41bdd88d2cb417fb72668658b4b5908eb22bdb2f0",
    "511adc7948119238825d9ff3aeb8c05c52f73c5fb6e2257aa3fcaac83b5b936d",
    "5ebaa3d6ae92a74345f6f62d75d7047e5aa1ae8de61e9a20ce408de675d250e8",
    "63a9ef0997bb8ceb5419605d0bad9f65fecdfab4ae2722472cfa1231f83a76ff",
    "6edb7769af3decab2a8a480cb8a548d236b52fd7946b3592025a5dd62aca3c7f",
    "77d4d2753effa570a462f45fda28c96fb9b0d72f96693b2d827e7c921af5f843",
    "79ce653c75ea2f6dcc6c6228b9af4b926a17a475dee3b465a035865be9e3b629",
    "8e4d14fda4d2f992f24eee580ecb773fb8da24933bad9b5fb287fc4dd849d2f2",
    "93c9addae0d9ed2ff6b04ddbf40e60ff849869fae21f8ea9bbf61865041eab7c",
    "9884c7f8b3100a536d85421dfea25496df5ec6d70296e9ecc963cc83b3e2ac3c",
    "b397e4b8ceddae74f0e017b729b2d0bfb2b2af1de8bcfdfb5722082186f94453",
    "c8aa3006c1098f06df0bc56ac57dfa4e46f597aa5f7c721818e4608d7d367d82",
    "cb7386106fc9a5c2969114c38d956a5430a45ad6c97c1508462b915c0e15cfe5",
    "e82cd4d1b623dbd0eca2fb4b477a554633b5ef8f9a9bab375aaa1fceafe98447",
    "eb228c2a0727ac5d6f93ed839ed308b43087d5bb7396bd11a2ba5bbb6964cd1c",
    "efb1d775e5527205ff1231b410827c32e987492258838c02358d6a56f0cc3989",
})


class PublicLibraryEligibilityError(ValueError):
    pass


def ensure_public_library_eligible(
    *,
    result: Result,
    extraction: DrawingExtraction,
    document_sha256: str | None,
    has_attestation: bool,
) -> None:
    if result.state != "completed" or result.review is None or not result.review.reviewer_name.strip():
        raise PublicLibraryEligibilityError("public_library_review_required")
    if not has_attestation:
        raise PublicLibraryEligibilityError("public_library_attestation_required")
    if extraction.synthetic:
        raise PublicLibraryEligibilityError("public_library_synthetic_forbidden")
    if not document_sha256:
        raise PublicLibraryEligibilityError("public_library_source_evidence_required")
    if document_sha256.lower() in KNOWN_BUNDLED_FIXTURE_SHA256:
        raise PublicLibraryEligibilityError("public_library_fixture_forbidden")


