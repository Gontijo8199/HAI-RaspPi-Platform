"""
Regra da atividade: divisores, primalidade e fatoração de um número inteiro.

Sem interface e sem serviços: a validação e o cálculo são testados direto
(tests/test_exemplo_logic.py). A tela só chama analyze() e mostra o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_NUMBER = 1_000_000  # acima disso a lista de divisores deixa de caber na tela


class InvalidInput(ValueError):
    """Entrada recusada. A mensagem é mostrada ao aluno como está."""


@dataclass(frozen=True)
class Analysis:
    number: int
    divisors: list[int]
    factors: list[tuple[int, int]]  # (primo, expoente), em ordem crescente

    @property
    def is_prime(self) -> bool:
        return len(self.divisors) == 2


def parse_number(text: str) -> int:
    """Converte o texto digitado num inteiro de 1 a MAX_NUMBER."""
    cleaned = text.strip()
    if not cleaned:
        raise InvalidInput("Digite um número para começar.")
    if cleaned.startswith("-"):
        raise InvalidInput("Use um número positivo: divisores e primos são de números naturais.")
    if not (cleaned.isascii() and cleaned.isdigit()):
        raise InvalidInput("Digite só algarismos, sem vírgula, ponto ou letras (por exemplo: 28).")
    number = int(cleaned)
    if number == 0:
        raise InvalidInput(
            "O zero é divisível por todos os números. Tente um número a partir de 1."
        )
    if number > MAX_NUMBER:
        raise InvalidInput(f"Use um número de até {MAX_NUMBER:,}.".replace(",", "."))
    return number


def divisors(number: int) -> list[int]:
    small, large = [], []
    d = 1
    while d * d <= number:
        if number % d == 0:
            small.append(d)
            if d != number // d:
                large.append(number // d)
        d += 1
    return small + large[::-1]


def factorize(number: int) -> list[tuple[int, int]]:
    factors = []
    p = 2
    while p * p <= number:
        exponent = 0
        while number % p == 0:
            number //= p
            exponent += 1
        if exponent:
            factors.append((p, exponent))
        p += 1
    if number > 1:
        factors.append((number, 1))
    return factors


def analyze(text: str) -> Analysis:
    """Valida o texto e calcula tudo. Levanta InvalidInput."""
    number = parse_number(text)
    return Analysis(number=number, divisors=divisors(number), factors=factorize(number))


_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def describe(result: Analysis) -> tuple[str, str]:
    """(veredito, detalhes) em português, prontos para a tela."""
    n = result.number
    listed = ", ".join(str(d) for d in result.divisors)
    count = len(result.divisors)
    if n == 1:
        return (
            "1 não é primo nem composto.",
            "Ele tem um único divisor: o próprio 1. Um número primo tem exatamente dois.",
        )
    if result.is_prime:
        return (
            f"{n} é primo.",
            f"Só é divisível por 1 e por ele mesmo. Divisores: {listed}.",
        )
    product = " × ".join(
        str(p) if e == 1 else f"{p}{str(e).translate(_SUPERSCRIPT)}" for p, e in result.factors
    )
    return (
        f"{n} não é primo: tem {count} divisores.",
        f"Divisores: {listed}.\nFatoração em primos: {n} = {product}.",
    )
