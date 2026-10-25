# Qing 
# 29th may 2017
'''
1. commit ROB_buffer
2. fetch header into ROB_buffer
'''

# function: print ROB entry 
def print_ROB(entry, instructions):
    item = instructions[entry.PC].ljust(30)
    item += str(entry.issue).ljust(15) 
    item += str(entry.exe).ljust(15) 
    item += str(entry.mem).ljust(15)
    item += str(entry.cdb).ljust(15)
    item += str(entry.commit)
    print(item)
# function: modify architectual reg
def modify_arch_reg(entry, reg_int, reg_fp):
    if entry.dest_tag[0] == 'F':
        reg_fp[int(entry.dest_tag[1:])] = entry.value
    elif entry.dest_tag[0] == 'R':
        reg_int[int(entry.dest_tag[1:])] = entry.value
    else:
        pass

# function: commit
def commit(ROB, reg_int, reg_fp, cycle, instructions,
           commit_width=1, ld_sd_queue=None, memory=None):

    for _ in range(commit_width):
        if not ROB:
            break

        entry = ROB[0]
        op = instructions[entry.PC].split()[0]

        if op == 'Bne':
            # EX records both its starting and finishing cycles.
            if len(entry.exe) < 2 or entry.exe[-1] >= cycle:
                break

        elif op == 'Sd':
            # MEM completes the access; only retirement changes memory.
            if not entry.store_complete:
                break
            if ld_sd_queue is None or memory is None:
                raise ValueError('store retirement requires the load/store queue and memory')
            if not ld_sd_queue or ld_sd_queue[0].dest_tag != entry.ROB_tag:
                raise RuntimeError('retiring store must be at the load/store queue head')
            store = ld_sd_queue[0]
            memory[store.address] = store.data
            ld_sd_queue.popleft()

        else:
            # ALU instructions and loads must have broadcast.
            if not entry.cdb or entry.cdb[-1] >= cycle:
                break

            modify_arch_reg(entry, reg_int, reg_fp)

        entry.commit.append(cycle)
        ROB.popleft()
        print_ROB(entry, instructions)
