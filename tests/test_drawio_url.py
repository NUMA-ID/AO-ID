# /home/numa/projets/appel-offre/tests/test_drawio_url.py
"""Tests de résolution d'URL draw.io (PREPROD port 8081 vs PROD préfixe /drawio)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from drawio_url import resolve_drawio_base  # noqa: E402


class ResolveDrawioBaseTests(unittest.TestCase):
    def test_override_gagne(self) -> None:
        self.assertEqual(
            resolve_drawio_base(
                override="https://ao-id.one-id.fr/drawio/",
                scheme="http",
                hostname="localhost",
                port="8080",
            ),
            "https://ao-id.one-id.fr/drawio",
        )

    def test_preprod_localhost_8080(self) -> None:
        self.assertEqual(
            resolve_drawio_base(scheme="http", hostname="localhost", port="8080"),
            "http://localhost:8081",
        )

    def test_preprod_127_0_0_1(self) -> None:
        self.assertEqual(
            resolve_drawio_base(scheme="http", hostname="127.0.0.1", port="8080"),
            "http://127.0.0.1:8081",
        )

    def test_prod_https_sans_port(self) -> None:
        self.assertEqual(
            resolve_drawio_base(scheme="https", hostname="ao-id.one-id.fr", port=""),
            "https://ao-id.one-id.fr/drawio",
        )

    def test_prod_https_443(self) -> None:
        self.assertEqual(
            resolve_drawio_base(scheme="https", hostname="ao-id.one-id.fr", port="443"),
            "https://ao-id.one-id.fr/drawio",
        )

    def test_ne_pas_pointer_le_meme_port_que_ao_id_en_prod(self) -> None:
        url = resolve_drawio_base(scheme="https", hostname="ao-id.one-id.fr", port="")
        self.assertNotIn(":8081", url)
        self.assertTrue(url.endswith("/drawio"))


if __name__ == "__main__":
    unittest.main()
