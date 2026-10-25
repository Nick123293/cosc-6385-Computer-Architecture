"""Regression checks for in-order retirement and commit-stage store writes."""

from collections import Counter, deque
import contextlib
import io
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import commit as commit_stage
from init import ROB_entry, ld_sd_mem
import input_parser
import issue as issue_stage
import mem as memory_stage


CODE_DIR = Path(__file__).resolve().parent
CASE_DIR = CODE_DIR.parent.parent / 'test_cases'


def rob_entry(index, destination='R1', wb_cycle=None, execution=None):
    entry = ROB_entry()
    entry.ROB_tag = f'ROB{index}'
    entry.PC = index
    entry.dest_tag = destination
    entry.value = index + 10
    entry.issue = [1]
    entry.exe = execution or []
    entry.cdb = [] if wb_cycle is None else [wb_cycle]
    return entry


def memory_entry(index, op='Sd', address=0, data=7, ready=1):
    return SimpleNamespace(
        ld_sd_tag=f'ldsd{index}', dest_tag=f'ROB{index}',
        op=op, address=address, data=data, ready=ready,
    )


class CommitOrderTests(unittest.TestCase):
    def setUp(self):
        self.reg_int = [0] * 32
        self.reg_fp = [0.0] * 32
        self.memory = [0] * 256
        self.port = ld_sd_mem()
        self.port.busy = 0
        self.print_patch = patch.object(commit_stage, 'print_ROB')
        self.print_patch.start()
        self.addCleanup(self.print_patch.stop)

    def test_older_unready_instruction_blocks_younger_ready_instruction(self):
        older, younger = rob_entry(0), rob_entry(1, 'R2', wb_cycle=2)
        ROB = deque([older, younger])
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 5,
                            ['Addi R1 R0 10', 'Addi R2 R0 11'], 4)
        self.assertEqual(list(ROB), [older, younger])
        self.assertEqual(self.reg_int, [0] * 32)

    def test_commit_waits_until_cycle_after_writeback_and_reports_actual_cycle(self):
        entry = rob_entry(0, wb_cycle=4)
        ROB = deque([entry])
        instructions = ['Addi R1 R0 10']
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 4, instructions)
        self.assertEqual(len(ROB), 1)
        self.assertEqual(entry.commit, [])
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 5, instructions)
        self.assertFalse(ROB)
        self.assertEqual(entry.commit, [5])
        self.assertEqual(self.reg_int[1], 10)

    def test_ready_instructions_respect_commit_width(self):
        entries = [rob_entry(i, f'R{i + 1}', wb_cycle=2) for i in range(3)]
        ROB = deque(entries)
        instructions = [f'Addi R{i + 1} R0 {i + 10}' for i in range(3)]
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 5, instructions, 2)
        self.assertEqual(list(ROB), [entries[2]])
        self.assertEqual([e.commit for e in entries], [[5], [5], []])

    def test_branch_retires_after_resolution_with_a_commit_timestamp(self):
        entry = rob_entry(0, execution=[2, 3])
        ROB = deque([entry])
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 3, ['Bne R1 R0 -4'])
        self.assertEqual(len(ROB), 1)
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 4, ['Bne R1 R0 -4'])
        self.assertFalse(ROB)
        self.assertEqual(entry.commit, [4])

    def test_store_cannot_start_behind_an_unready_rob_head(self):
        older, store = rob_entry(0), rob_entry(1, 'ldsd1')
        ROB = deque([older, store])
        queue = deque([memory_entry(1, address=64)])
        for cycle in range(2, 6):
            memory_stage.mem(queue, self.port, 1, deque(), self.memory, ROB, cycle)
        self.assertEqual(self.memory[64], 0)
        self.assertEqual(len(queue), 1)
        self.assertFalse(self.port.busy)
        self.assertFalse(store.store_complete)
        self.assertEqual(store.commit, [])

    def test_store_waits_for_both_address_and_data(self):
        for ready, data in ((0, 7), (1, 'ROB7')):
            with self.subTest(ready=ready, data=data):
                store = rob_entry(0, 'ldsd0')
                queue = deque([memory_entry(0, ready=ready, data=data)])
                memory_stage.mem(queue, self.port, 1, deque(), self.memory,
                                 deque([store]), 2)
                self.assertFalse(self.port.busy)
                self.assertEqual(len(queue), 1)

    def test_multicycle_store_stays_queued_and_writes_only_during_commit(self):
        store = rob_entry(0, 'ldsd0')
        ROB = deque([store])
        queue = deque([memory_entry(0, address=64, data=5)])
        instructions = ['Sd F1 64(R0)']
        for cycle in range(1, 5):
            memory_stage.mem(queue, self.port, 3, deque(), self.memory, ROB, cycle)
            self.assertEqual(self.memory[64], 0)
            self.assertEqual(len(queue), 1)
            self.assertEqual(store.commit, [])
            if cycle < 4:
                commit_stage.commit(ROB, self.reg_int, self.reg_fp, cycle,
                                    instructions, 4, queue, self.memory)
                self.assertEqual(len(ROB), 1)
        self.assertTrue(store.store_complete)
        self.assertEqual(store.mem, [2, 4])
        self.assertFalse(self.port.busy)
        commit_stage.commit(ROB, self.reg_int, self.reg_fp, 4,
                            instructions, 4, queue, self.memory)
        self.assertEqual(self.memory[64], 5)
        self.assertEqual(store.commit, [4])
        self.assertFalse(ROB)
        self.assertFalse(queue)

    def test_store_head_check_handles_empty_and_single_entry_queues(self):
        check = memory_stage.check_if_sd_committable
        self.assertFalse(check(deque(), deque()))
        queue, ROB = deque([memory_entry(0)]), deque([rob_entry(0, 'ldsd0')])
        self.assertFalse(check(queue, deque()))
        self.assertTrue(check(queue, ROB))
        ROB[0].store_complete = True
        self.assertFalse(check(queue, ROB))

    def test_forwarding_uses_youngest_matching_store_past_unrelated_stores(self):
        queue = deque([
            memory_entry(0, address=0, data=11),
            memory_entry(1, address=0, data=22),
            memory_entry(2, address=4, data=33),
            memory_entry(3, op='Ld', address=0),
        ])
        self.assertEqual(memory_stage.forward_check_from_sd(queue, 3), [22])
        queue[1].data = 'ROB7'
        self.assertEqual(memory_stage.forward_check_from_sd(queue, 3), [])
        queue[1].data, queue[2].ready = 22, 0
        self.assertEqual(memory_stage.forward_check_from_sd(queue, 3), [])

    def test_multiple_loads_forward_while_store_waits_for_retirement(self):
        ROB = deque([rob_entry(i) for i in range(4)])
        queue = deque([memory_entry(1), memory_entry(2, op='Ld'),
                       memory_entry(3, op='Ld')])
        results = deque()
        memory_stage.mem(queue, self.port, 1, results, self.memory, ROB, 3)
        self.assertEqual([e.value for e in results], [7, 7])
        self.assertEqual([e.mem for e in list(ROB)[2:]], [[3], [3]])
        self.assertEqual(len(queue), 1)
        self.assertFalse(self.port.busy)
        self.assertEqual(self.memory[0], 0)

    def test_load_can_bypass_unrelated_store_waiting_for_rob_head(self):
        ROB = deque([rob_entry(i) for i in range(3)])
        queue = deque([memory_entry(1, address=0),
                       memory_entry(2, op='Ld', address=4)])
        results = deque()
        self.memory[4] = 42
        memory_stage.mem(queue, self.port, 1, results, self.memory, ROB, 3)
        self.assertEqual(self.port.op, 'Ld')
        memory_stage.mem(queue, self.port, 1, results, self.memory, ROB, 4)
        self.assertEqual([e.value for e in results], [42])
        self.assertEqual(len(queue), 1)
        self.assertEqual(self.memory[0], 0)


def sequential_result(program):
    """Independent architectural reference, using the existing byte offsets."""
    integers, floating, memory = program.reg_int[:], program.reg_fp[:], program.memory[:]
    pc = 0
    def operand(register):
        return (integers if register[0] == 'R' else floating)[int(register[1:])]
    for _ in range(2000):
        if pc >= len(program.instructions):
            return integers, floating, memory
        op, *args = program.instructions[pc].split()
        next_pc = pc + 1
        if op in ('Ld', 'Sd'):
            offset, base = args[1][:-1].split('(')
            address = int(offset) + operand(base)
            if op == 'Ld':
                floating[int(args[0][1:])] = memory[address]
            else:
                memory[address] = operand(args[0])
        elif op == 'Bne':
            if operand(args[0]) != operand(args[1]):
                next_pc = int(pc + 1 + int(args[2]) / 4)
        else:
            left = operand(args[1])
            right = int(args[2]) if op == 'Addi' else operand(args[2])
            if op in ('Add', 'Addi', 'Add.d'):
                value = left + right
            elif op in ('Sub', 'Sub.d'):
                value = left - right
            else:
                value = left * right
            target = integers if args[0][0] == 'R' else floating
            target[int(args[0][1:])] = value
        pc = next_pc
    raise AssertionError('reference program did not terminate')


class ProgramOrderTests(unittest.TestCase):
    def simulate(self, filename, width):
        read_original = input_parser.read_input
        issue_original, mem_original = issue_stage.issue, memory_stage.mem
        commit_original = commit_stage.commit
        expected = sequential_result(read_original(filename))
        issued, retired, writes = [], [], []
        context = {}

        class ObservedMemory(list):
            def __setitem__(memory, address, value):
                self.assertEqual(context['stage'], 'COMMIT')
                head = context['ROB'][0]
                self.assertTrue(head.store_complete)
                self.assertTrue(context['instructions'][head.PC].startswith('Sd '))
                writes.append((context['cycle'], head.PC, address, value))
                super().__setitem__(address, value)

        def read_case(path):
            program = read_original(path)
            program.issue_width = width
            program.memory = ObservedMemory(program.memory)
            context['instructions'] = program.instructions
            return program

        def observe_issue(cycle, PC, instructions, ROB, *args):
            count = len(ROB)
            issue_original(cycle, PC, instructions, ROB, *args)
            if len(ROB) > count:
                issued.append(ROB[-1])

        def observe_mem(queue, port, latency, results, memory, ROB, cycle):
            context.update(stage='MEM', cycle=cycle, ROB=ROB)
            mem_original(queue, port, latency, results, memory, ROB, cycle)

        def observe_commit(ROB, ri, rf, cycle, instructions, *args, **kwargs):
            self.assertLess(cycle, 2000, 'simulator did not terminate')
            context.update(stage='COMMIT', cycle=cycle, ROB=ROB)
            commit_original(ROB, ri, rf, cycle, instructions, *args, **kwargs)

        def observe_retirement(entry, instructions):
            self.assertIs(entry, issued[len(retired)], 'ROB retirement skipped an older instruction')
            self.assertEqual(entry.commit, [context['cycle']])
            op = instructions[entry.PC].split()[0]
            if op not in ('Sd', 'Bne'):
                self.assertLess(entry.cdb[-1], entry.commit[0])
            elif op == 'Bne':
                self.assertLess(entry.exe[-1], entry.commit[0])
            retired.append((entry.PC, op, entry.commit[0]))

        with patch.object(input_parser, 'read_input', read_case), \
                patch.object(issue_stage, 'issue', observe_issue), \
                patch.object(memory_stage, 'mem', observe_mem), \
                patch.object(commit_stage, 'commit', observe_commit), \
                patch.object(commit_stage, 'print_ROB', observe_retirement), \
                patch.object(sys, 'argv', [str(CODE_DIR / 'main.py'), str(filename)]), \
                contextlib.redirect_stdout(io.StringIO()):
            state = runpy.run_path(str(CODE_DIR / 'main.py'))

        self.assertEqual(len(issued), len(retired))
        self.assertEqual([cycle for _, _, cycle in retired], sorted(cycle for _, _, cycle in retired))
        self.assertLessEqual(max(Counter(cycle for _, _, cycle in retired).values()), width)
        self.assertEqual(len(writes), sum(op == 'Sd' for _, op, _ in retired))
        self.assertEqual([(pc, cycle) for cycle, pc, _, _ in writes],
                         [(pc, cycle) for pc, op, cycle in retired if op == 'Sd'])
        self.assertTrue(all(count <= 1 for count in Counter(cycle for cycle, _, _, _ in writes).values()))
        actual = state['reg_int'], state['reg_fp'], list(state['memory'])
        self.assertEqual(actual, expected)
        return {'cycles': state['cycle'] - 1, 'retired': retired, 'writes': writes}

    def test_bundled_programs_retire_in_order_and_match_reference_at_all_widths(self):
        for filename in ('test_case.txt', 'test_case2.txt'):
            for width in (1, 2, 3, 4):
                with self.subTest(filename=filename, width=width):
                    self.simulate(CASE_DIR / filename, width)

    def test_multiple_aliasing_stores_loads_and_final_store_at_all_widths(self):
        source = '''
            Integer adder 2 1 1
            FP adder 2 3 1
            FP multiplier 2 15 1
            Load/store unit 5 1 3 1
            F1=2.0, F2=3.0
            Mem[12]=9.0
            Mult.d F8 F1 F2
            Sd F1 0(R0)
            Sd F2 4(R0)
            Ld F3 0(R0)
            Sd F2 0(R0)
            Ld F4 0(R0)
            Ld F5 4(R0)
            Sd F3 8(R0)
            Sd F0 12(R0)
        '''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stores.txt'
            path.write_text(source)
            for width in (1, 2, 3, 4):
                with self.subTest(width=width):
                    self.simulate(path, width)


if __name__ == '__main__':
    unittest.main()
