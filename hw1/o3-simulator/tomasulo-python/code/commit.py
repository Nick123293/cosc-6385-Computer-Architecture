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
           commit_width=1):

    for _ in range(commit_width):
        if not ROB:
            break

        entry = ROB[0]
        op = instructions[entry.PC].split()[0]

        if op == 'Bne':
            # EX records both its starting and finishing cycles.
            if len(entry.exe) < 2:
                break

        elif op == 'Sd':
            # Preserve the simulator's existing store-ready marker.
            if not entry.commit:
                break

        else:
            # ALU instructions and loads must have broadcast.
            if not entry.cdb:
                break

            entry.commit.append(cycle + 1)
            modify_arch_reg(entry, reg_int, reg_fp)

        ROB.popleft()
        print_ROB(entry, instructions)
