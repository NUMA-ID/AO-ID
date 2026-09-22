# /home/numa/projets/appel-offre/tests/test_index_drawio.py
"""Garde-fous sur le frontend : draw.io ne doit plus cibler :8081 en PROD."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "app" / "web" / "index.html"


class IndexDrawioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = INDEX.read_text(encoding="utf-8")

    def test_placeholder_injection(self) -> None:
        self.assertIn("__DRAWIO_BASE__", self.html)

    def test_fallback_prod_prefixe(self) -> None:
        self.assertIn("location.origin+'/drawio'", self.html)

    def test_postmessage_compare_origin_pas_le_chemin(self) -> None:
        self.assertIn("new URL(DRAWIO_BASE", self.html)
        self.assertNotIn("DRAWIO_BASE.indexOf(evt.origin)", self.html)

    def test_libs_servies_par_ao_id(self) -> None:
        self.assertIn("location.origin+'/drawio-libs/'", self.html)

    def test_pas_uniquement_port_8081_en_dur(self) -> None:
        # Le port 8081 reste le fallback PREPROD, mais plus la seule URL.
        self.assertTrue(re.search(r"location\.origin\s*\+\s*'/drawio'", self.html))


if __name__ == "__main__":
    unittest.main()
