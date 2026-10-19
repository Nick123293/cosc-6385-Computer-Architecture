Tomasulo Algorithm Simulation
* includes instructions of int_add, fp_add, fp_multi, load, store, branch;
* implements ROB, RAT, load-store-queue;
* implements out-of-order processing and memory disambiguation; 
* doesn't include branch prediction.

How to run:
```sh
cd code
python main.py                  # reads the bundled test_case.txt
python main.py path/to/case.txt # reads another input file
```

Inputs use the format in `code/test_case.txt`: hardware rows, `ROB entries`,
an optional `Issue width` (1–4, default 1), register/memory initializers, and
assembly instructions. For example:

```text
               # of rs         Cycles in EX    Cycles in Mem   # of FUs
Integer adder   4               1                               1
FP adder        3               4                               1
FP multiplier   2               15                              1
Load/store unit 5               1               5               1

ROB entries = 64
Issue width = 2
R1=12, F20=3.0
Mem[12]=1.0

Ld F2, 0(R1)
Mult.d F4, F2, F20
```

Settings and instructions are case insensitive. Blank lines and `#` comments
are ignored; assembly commas are optional. Omitted registers and memory values
start at zero. Omitted hardware settings retain the original simulator defaults
shown above. Instruction-only files are also accepted, using those defaults and
zero-initialized registers/memory.

The existing simulator has one functional unit of each type. The parser checks
the `# of FUs` column and rejects counts other than 1. It supports the simulator's
existing instructions and branch-offset convention.

After the instruction timing table, output lists all integer and FP registers
and nonzero memory values with their byte addresses. A final store is allowed to
finish before memory is printed. Issue width also controls commit width.
