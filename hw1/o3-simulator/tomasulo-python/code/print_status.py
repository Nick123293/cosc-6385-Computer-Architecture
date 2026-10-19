# Qing 
# 21st May 2017

# function: print RS/ROB status
def ps(unit):
    if(len(unit)==0):
        print('empty!')
    else:
        # get all fields in namedtuple
        fields_list = unit[0]._fields
        for unit_item in unit:
            print ('******')
            for field in fields_list:
                print(field+': ', str(getattr(unit_item, field)))

# function: print single namedtuple
def pss(snt):
    fields_list = snt._fields
    for field in fields_list:
        print (field+': ', str(getattr(snt, field)))


def print_final_state(reg_int, reg_fp, memory):
    """Print committed register values and nonzero byte-addressed memory."""
    print('\nREGISTER VALUES')
    for prefix, registers in (('R', reg_int), ('F', reg_fp)):
        for start in range(0, len(registers), 8):
            indices = range(start, min(start + 8, len(registers)))
            print(''.ljust(8) + ''.join(
                f'{prefix}{index}'.rjust(12) for index in indices
            ))
            print('value:'.ljust(8) + ''.join(
                str(registers[index]).rjust(12) for index in indices
            ))

    print('\nNON-ZERO MEMORY VALUES')
    print('Address'.ljust(12) + 'Value')
    nonzero = [(address, value) for address, value in enumerate(memory) if value != 0]
    for address, value in nonzero:
        print(str(address).ljust(12) + str(value))
    if not nonzero:
        print('(none)')

