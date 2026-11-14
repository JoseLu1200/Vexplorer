from __future__ import annotations

from backend.app.contratos.modelos import DrawingExtraction, Result


# Include LF and CRLF bytes: Git checkouts differ between Linux and Windows.
KNOWN_BUNDLED_FIXTURE_SHA256 = frozenset({
    "01d1ad36566fc1816db122e9ba6c3e421359bfd81ef6d44620a8f5fe100ef810",
    "3163bdb47f2ac7642ce951f6b0d10ef5511d57ba779e7e0fb983c9bd17461aa9",
    "32a4a0b31056d28b42409a3abdb1fb9658547165a4076ad7372a2ea2da7c418f",
    "37c7aad2fdc7910ca309e9edbb0713aec6d5ac51fd5be1ac33fa189c4e508c83",
    "3f9fe1582215eb99f870d8bb889e1cfbb8b92fdd84721ccfcbbf6f5027613790",
    "4160b7cb7b50c1aed7777aecfc401b7036d09b9cde129f7ef533f228a678389a",
    "53c0e876bf843ec509f73cf2962a60eac543ad425d747b78dda5076dfe38dc9c",
    "54ff4be08107b27f7cd73eb2f3785446bf0c3087cdfc473a855a645ff49730b5",
    "68a94d8071fc3d8f627b2795784b71aa3d3b5a8774ea9a2c1d22273b635b139d",
    "6e6e3562e39514ffbce52b85122851f5dc68b79cc13b925f2e1d1462de5cd333",
    "7e7fb3f4866ad8a92dcb5a19cf92fc9e3cbbfdc8bc13e21a76415c3c5d1ca8c8",
    "90f4a912e4dd6a235f875bfd543ab543b2d384a5d7168c0c74829efafe9117a2",
    "9ebe94d26aef22115dbdb096a41bfc4cace3db80513955c454fad94918ad0c15",
    "a94a01bbc32e3c82f1d70b023003da500f67af58a700ee27936dd2b8cb78d63d",
    "aee41791fbc4b4c4922e3b0acb5d0e1ab4d0afcc390e7e08309bb6f7d0f5e490",
    "be51cc107238f71ac806d641e0ddfc5950caf97ccaf5176d425a5ec94cc79ffa",
    "ce4100d754010ad439a0b868a2f2465713fd2b206df95d9f29170f2aa9a19bae",
    "e0abe4221badb5c0eff2ca049459aa637348bae50fa2af5a815e65ee87ab1d71",

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


