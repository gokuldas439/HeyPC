"""Spoken arithmetic. Parsed with a strict allow-list, so nothing heard can ever run as code."""
import ast
import operator
import re

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
HUNDRED = {"hundred": 100}
LARGE = {"thousand": 1_000, "k": 1_000, "lakh": 100_000, "lakhs": 100_000, "million": 1_000_000, "crore": 10_000_000, "crores": 10_000_000}
OPERATOR_WORDS = [
    ("multiplied by", "*"), ("divided by", "/"), ("to the power of", "**"), ("raised to", "**"), ("power of", "**"),
    ("times", "*"), ("into", "*"), ("plus", "+"), ("minus", "-"), ("over", "/"),
]
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
MAX_EXPONENT = 64
SIZE_LIMIT = 1e30
WORD_FORMS = [
    (re.compile(r"^add\s+(.+?)\s+(?:and|to)\s+(.+)$"), "{0} + {1}"),
    (re.compile(r"^subtract\s+(.+?)\s+from\s+(.+)$"), "{1} - {0}"),
    (re.compile(r"^multiply\s+(.+?)\s+(?:by|and)\s+(.+)$"), "{0} * {1}"),
    (re.compile(r"^divide\s+(.+?)\s+by\s+(.+)$"), "{0} / {1}"),
]


def _with_digits(text: str) -> str:
    """Turns "two lakh fifty thousand" into 250000 and leaves everything else alone."""
    output: list[str] = []
    total = current = 0
    in_number = False

    def flush() -> None:
        nonlocal total, current, in_number
        if in_number:
            output.append(str(total + current))
        total = current = 0
        in_number = False

    for word in text.split():
        if word in UNITS:
            current += UNITS[word]
            in_number = True
        elif word in HUNDRED and in_number:
            current = max(current, 1) * 100
        elif word in LARGE and in_number:
            total += max(current, 1) * LARGE[word]
            current = 0
        elif word == "and" and in_number:
            continue
        else:
            flush()
            output.append(word)
    flush()
    return " ".join(output)


def _to_expression(text: str) -> str:
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower()).strip(" ?.!")
    text = re.sub(r"(\d)\s*k\b", r"\1 k", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(thousand|k|lakhs?|million|crores?)\b", lambda m: str(float(m[1]) * LARGE[m[2]]), text)
    text = _with_digits(text)
    for form, template in WORD_FORMS:
        if match := form.match(text):
            text = template.format(match[1], match[2])
            break
    for phrase, symbol in OPERATOR_WORDS:
        text = re.sub(rf"\b{phrase}\b", f" {symbol} ", text)
    text = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", text)
    text = re.sub(r"\bsquare root of\s+([\d.]+)", r"(\1 ** 0.5)", text)
    text = re.sub(r"([\d.]+)\s+squared\b", r"(\1 ** 2)", text)
    text = re.sub(r"([\d.]+)\s+cubed\b", r"(\1 ** 3)", text)
    text = re.sub(r"([\d.]+)\s*(?:percent|%)\s+of\s+", r"(\1 / 100) * ", text)
    text = re.sub(r"([\d.]+)\s*([+-])\s*([\d.]+)\s*(?:percent|%)", r"\1 \2 (\1 * \3 / 100)", text)
    return re.sub(r"([\d.]+)\s*(?:percent|%)", r"(\1 / 100)", text)


def _compute(node):
    if isinstance(node, ast.Expression):
        return _compute(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_compute(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        left, right = _compute(node.left), _compute(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError("exponent too large")
        result = BINARY[type(node.op)](left, right)
        if isinstance(result, complex) or abs(result) > SIZE_LIMIT:
            raise ValueError("result out of range")
        return result
    raise ValueError("not arithmetic")


def evaluate(text: str) -> float | None:
    """The answer, or None if this isn't a sum. A bare number doesn't count."""
    expression = _to_expression(text)
    if not re.fullmatch(r"[\d.\s+\-*/()]+", expression) or not re.search(r"[+\-*/]", expression):
        return None
    try:
        return float(_compute(ast.parse(expression.strip(), mode="eval")))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None


def spoken_number(value: float) -> str:
    rounded = round(value, 4)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.4f}".rstrip("0")
