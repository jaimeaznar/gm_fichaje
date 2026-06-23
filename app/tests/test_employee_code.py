"""Generación de código de empleado (REQ-05). Casos de references/codigo-pin.md."""

from __future__ import annotations

from itertools import islice

import pytest

from app.domain.employee_code import candidate_codes, first_token, normalize


def first_code(nombre: str, apellido: str) -> str:
    return next(candidate_codes(nombre, apellido))


def test_normalize_strips_accents_and_nonletters():
    assert normalize("José") == "jose"
    assert normalize("Peña") == "pena"
    assert normalize("Núñez") == "nunez"
    assert normalize("O'Brien-2") == "obrien"


def test_first_token_for_compound_names():
    assert first_token("José Luis") == "José"


def test_base_code_pepe_garcia():
    assert first_code("Pepe", "Garcia") == "PeGa"


def test_accents_removed_in_code():
    assert first_code("José", "Núñez") == "JoNu"


def test_escalation_levels_for_collisions():
    # Pepe Garcia: PeGa -> PepGar -> PepeGarc -> ...
    codes = list(islice(candidate_codes("Pepe", "Garcia"), 3))
    assert codes[0] == "PeGa"
    assert codes[1] == "PepGar"
    assert codes[2] == "PepeGarc"


def test_numeric_suffix_after_exhausting_letters():
    # Pa Li: solo nivel 2 -> luego sufijo numérico PaLi2, PaLi3...
    codes = list(islice(candidate_codes("Pa", "Li"), 3))
    assert codes == ["PaLi", "PaLi2", "PaLi3"]


def test_penelope_garza_level_two():
    codes = list(islice(candidate_codes("Penelope", "Garza"), 2))
    assert codes[0] == "PeGa"
    assert codes[1] == "PenGar"


def test_empty_name_raises():
    with pytest.raises(ValueError):
        next(candidate_codes("123", "Garcia"))
