# Qing 
# 21st May 2017 

from copy import deepcopy
import argparse
from pathlib import Path
from collections import deque, namedtuple
from init import build_rs, ld_sd_entry, ld_sd_exe, ld_sd_mem, cdb, ROB_entry, PC
from input_parser import read_input
from print_status import ps, pss, print_final_state
from issue import issue, check_rs_space
from exe import exe 
from mem import mem
from wb import wb 
from commit import commit
'''initialize'''
argument_parser = argparse.ArgumentParser(description='Run the Tomasulo simulator.')
argument_parser.add_argument(
    'input_file', nargs='?', type=Path,
    default=Path('../../test_cases/test_case.txt'),
    help='configuration and assembly file (default: bundled test_case.txt)',
)
arguments = argument_parser.parse_args()
try:
    program = read_input(arguments.input_file)
except (OSError, ValueError) as error:
    argument_parser.error(str(error))

instructions = program.instructions
issue_width = program.issue_width
'''initialize regs, RAT, memory''' 
# integer REG
reg_int = program.reg_int
rat_int = deepcopy(reg_int)
# fp REG
reg_fp = program.reg_fp
rat_fp = deepcopy(reg_fp)
# memory 
memory = program.memory
'''intialize reservation stations'''
size_rs_int_adder = program.units['integer adder'].rs
rs_int_adder = build_rs(size_rs_int_adder)
size_rs_fp_adder = program.units['fp adder'].rs
rs_fp_adder = build_rs(size_rs_fp_adder)
size_rs_fp_multi = program.units['fp multiplier'].rs
rs_fp_multi = build_rs(size_rs_fp_multi)
'''initilize function unit'''
fu_int_adder = deque()
time_fu_int_adder = program.units['integer adder'].ex_cycles
fu_fp_adder = deque()
time_fu_fp_adder = program.units['fp adder'].ex_cycles
fu_fp_multi = deque()
time_fu_fp_multi = program.units['fp multiplier'].ex_cycles
'''initialize load/store queue'''
ld_sd_queue = deque()
size_ld_sd_queue = program.units['load/store unit'].rs
ld_sd_exe = ld_sd_exe()
ld_sd_exe.busy = 0
time_ld_sd_exe = program.units['load/store unit'].ex_cycles
ld_sd_mem = ld_sd_mem()
ld_sd_mem.busy = 0
time_ld_sd_mem = program.units['load/store unit'].mem_cycles
'''initialize ROB'''
ROB = deque()
size_ROB = program.rob_entries
'''initialize CDB'''
results_buffer = deque()
cdb = cdb()
cdb.valid = 0
"""issue first instruction"""
# instruction pointer 
PC = PC()
PC.PC = 0
PC.valid = 1 
cycle = 1

# print title 
item = ''.ljust(30)
item += 'ISSUE'.ljust(15)
item += 'EXE'.ljust(15)
item += 'MEM'.ljust(15)
item += 'WB'.ljust(15)
item += 'COMMIT'.ljust(15)
print (item)

# main
# Drain the final memory operation before reporting the final memory values.
while PC.PC < len(instructions) or ROB or ld_sd_mem.busy:
    
    '''ISSUE stage'''
    for _ in range(issue_width):
        if PC.PC >= len(instructions) or PC.valid != 1:
            break

        previous_pc = PC.PC

        issue(cycle, PC, instructions, ROB, size_ROB,
              rs_int_adder,
              rs_fp_adder,
              rs_fp_multi,
              ld_sd_queue, size_ld_sd_queue,
              rat_int, rat_fp)

        if PC.PC == previous_pc:
            break

    '''EXE stage'''
    exe(fu_int_adder, time_fu_int_adder, 
        fu_fp_adder, time_fu_fp_adder, 
        fu_fp_multi, time_fu_fp_multi, results_buffer,  
        rs_int_adder, rs_fp_adder, rs_fp_multi, 
        ld_sd_exe, time_ld_sd_exe, ld_sd_queue,
        cycle, ROB, PC)

    '''MEM stage'''
    mem(ld_sd_queue, ld_sd_mem, time_ld_sd_mem, results_buffer,
        memory, ROB, cycle)

    '''CDB stage'''
    wb(cdb, rat_int, rat_fp, 
        rs_int_adder, rs_fp_adder, rs_fp_multi,
        ld_sd_queue, ROB, cycle,
        results_buffer) 
    
    '''COMMIT stage'''
    commit(ROB, reg_int, reg_fp, cycle, instructions, issue_width)
    
    # cycle number 
    cycle +=1  

print_final_state(reg_int, reg_fp, memory)
