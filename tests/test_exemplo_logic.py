"""Regra do módulo de exemplo (modules/exemplo/logic.py): sem Qt, sem serviços."""

import pytest

from modules.exemplo.logic import (
    MAX_NUMBER,
    InvalidInput,
    analyze,
    describe,
    divisors,
    factorize,
    parse_number,
)


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, [1]), (7, [1, 7]), (12, [1, 2, 3, 4, 6, 12]), (36, [1, 2, 3, 4, 6, 9, 12, 18, 36])],
)
def test_divisores_em_ordem(number, expected):
    assert divisors(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [(2, [(2, 1)]), (360, [(2, 3), (3, 2), (5, 1)]), (999983, [(999983, 1)]), (1, [])],
)
def test_fatoracao(number, expected):
    assert factorize(number) == expected


def test_primo():
    result = analyze("13")
    assert result.is_prime
    verdict, details = describe(result)
    assert verdict == "13 é primo."
    assert "1, 13" in details


def test_composto_mostra_divisores_e_fatoracao():
    verdict, details = describe(analyze("28"))
    assert verdict == "28 não é primo: tem 6 divisores."
    assert "1, 2, 4, 7, 14, 28" in details
    assert "28 = 2² × 7" in details


def test_um_nao_e_primo_nem_composto():
    result = analyze("1")
    assert not result.is_prime
    assert "nem composto" in describe(result)[0]


def test_espacos_em_volta_sao_ignorados():
    assert parse_number("  42 \n") == 42


def test_limite_superior_aceito():
    assert parse_number(str(MAX_NUMBER)) == MAX_NUMBER


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("", "Digite um número"),
        ("   ", "Digite um número"),
        ("-5", "positivo"),
        ("3,5", "só algarismos"),
        ("12a", "só algarismos"),
        ("²", "só algarismos"),  # dígito Unicode que int() não aceitaria
        ("0", "zero"),
        (str(MAX_NUMBER + 1), "até 1.000.000"),
    ],
)
def test_entradas_invalidas_explicam_o_motivo(text, fragment):
    with pytest.raises(InvalidInput, match=fragment):
        analyze(text)
