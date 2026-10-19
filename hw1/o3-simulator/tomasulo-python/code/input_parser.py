"""Read hardware settings, initial values, and assembly from a test case."""

from dataclasses import dataclass, field
import math
import re


@dataclass
class UnitConfig:
    rs: int
    ex_cycles: int
    mem_cycles: int = 0
    fu_count: int = 1


def default_units():
    return {
        'integer adder': UnitConfig(4, 1),
        'fp adder': UnitConfig(3, 4),
        'fp multiplier': UnitConfig(2, 15),
        'load/store unit': UnitConfig(5, 1, 5),
    }


@dataclass
class SimulationInput:
    units: dict = field(default_factory=default_units)
    rob_entries: int = 64
    issue_width: int = 1
    reg_int: list = field(default_factory=lambda: [0] * 32)
    reg_fp: list = field(default_factory=lambda: [0.0] * 32)
    memory: list = field(default_factory=lambda: [0] * 256)
    instructions: list = field(default_factory=list)


OPCODES = {op.lower(): op for op in (
    'Ld', 'Sd', 'Add', 'Addi', 'Sub', 'Add.d', 'Sub.d', 'Mult.d', 'Bne'
)}
UNIT_ROW = re.compile(
    r'(Integer\s+adder|FP\s+adder|FP\s+multiplier|Load/store\s+unit)\s+(.+)',
    re.IGNORECASE,
)
SETTING = re.compile(r'(ROB\s+entries|Issue\s+width)\s*=\s*(\S+)', re.IGNORECASE)
ASSIGNMENT = re.compile(r'(R\d+|F\d+|Mem\[\d+\])\s*=\s*(\S+)', re.IGNORECASE)


def parse_number(value):
    if re.fullmatch(r'[+-]?\d+', value):
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('initial values must be finite numbers')
    return number


def read_input(filename):
    """Return defaults overridden by the settings and values in filename.

    Missing register and memory initializers leave those entries at zero.
    Assembly is normalized to the spacing and capitalization used by issue.py.
    """
    program = SimulationInput()
    with open(filename) as source:
        for line_number, raw_line in enumerate(source, 1):
            line = raw_line.split('#', 1)[0].strip()
            if not line:
                continue

            try:
                row = UNIT_ROW.fullmatch(line)
                if row:
                    name = ' '.join(row[1].lower().split())
                    columns = row[2].split()
                    expected = 4 if name == 'load/store unit' else 3
                    if len(columns) != expected:
                        raise ValueError(
                            f'{name} requires {expected} numeric columns'
                        )
                    values = [int(column) for column in columns]
                    if any(value < 1 for value in values):
                        raise ValueError('hardware settings must be positive integers')
                    if values[-1] != 1:
                        raise ValueError(
                            'this simulator supports exactly one FU per unit type'
                        )
                    program.units[name] = UnitConfig(
                        rs=values[0], ex_cycles=values[1],
                        mem_cycles=values[2] if expected == 4 else 0,
                        fu_count=values[-1],
                    )
                    continue

                setting = SETTING.fullmatch(line)
                if setting:
                    name = ' '.join(setting[1].lower().split())
                    value = int(setting[2])
                    if name == 'issue width':
                        if not 1 <= value <= 4:
                            raise ValueError('issue width must be between 1 and 4')
                        program.issue_width = value
                    else:
                        if value < 1:
                            raise ValueError('ROB entries must be positive')
                        program.rob_entries = value
                    continue

                if '=' in line:
                    for assignment in line.split(','):
                        match = ASSIGNMENT.fullmatch(assignment.strip())
                        if not match:
                            raise ValueError(f'invalid assignment: {assignment.strip()}')
                        name, literal = match[1].upper(), match[2]
                        value = parse_number(literal)
                        if name.startswith('MEM['):
                            address = int(name[4:-1])
                            if not 0 <= address < len(program.memory):
                                raise ValueError('memory address must be between 0 and 255')
                            program.memory[address] = value
                        else:
                            index = int(name[1:])
                            if not 0 <= index < 32:
                                raise ValueError('register index must be between 0 and 31')
                            if name.startswith('R'):
                                if not re.fullmatch(r'[+-]?\d+', literal):
                                    raise ValueError('integer registers require integer values')
                                if index == 0 and value != 0:
                                    raise ValueError('R0 must be initialized to zero')
                                program.reg_int[index] = value
                            else:
                                program.reg_fp[index] = float(value)
                    continue

                tokens = line.replace(',', ' ').split()
                op = OPCODES.get(tokens[0].lower())
                if op is None:
                    raise ValueError(f'unknown instruction or setting: {tokens[0]}')
                expected = 3 if op in ('Ld', 'Sd') else 4
                if len(tokens) != expected:
                    raise ValueError(f'{op} requires {expected - 1} operands')
                program.instructions.append(' '.join(
                    [op] + [operand.upper() for operand in tokens[1:]]
                ))
            except ValueError as error:
                raise ValueError(f'{filename}:{line_number}: {error}') from error

    return program
