# Qing 
# 26th May 2017

''' 
1. Ld forward check from older stores in ld_sd_queue
    -- use the youngest matching store with ready data
2. execute LD/SD instruction in ld_sd_mem
    -- once LD instruction gets data, write back to ld_sd_queue
    -- LD instruction should be removed after get data  
    -- stores remain queued and write memory only at commit
3. fetch new LD/SD instruction into ld_sd_mem
    -- if first element is SD, ready and has valid data, only SD to be committed can be fetched into ld_sd_mem 
    -- else put the first no-matched Ld into ld_sd_mem    
'''
from init import fu_result

# function: forward check from sd
def forward_check_from_sd(ld_sd_queue, index):
    for i in reversed(range(index)):
        store = ld_sd_queue[i]
        if store.op == 'Sd':
            if not store.ready:
                return []
            if store.address == ld_sd_queue[index].address:
                if isinstance(store.data, (int, float)):
                    return [store.data]
                return []
    return []

# function: check if previous all Sds are ready and un-matched
def check_all_previous_Sd_no_match(ld_sd_queue, index):
    flag = True
    for i in range(index):
        # all Sd instructions
        if (ld_sd_queue[i].op=='Sd'):
            if ld_sd_queue[i].ready == 0:
                flag = False
                break 
            elif (ld_sd_queue[i].address==ld_sd_queue[index].address):
                flag = False
                break
            else:
                pass
    return flag
 
# function: find ROB entry by tag
def find_ROB_entry(ROB, tag):
    for index in range(len(ROB)):
        if ROB[index].ROB_tag == tag:
            break
    return index

# function: put entry into ld_sd_mem
def put_entry_into_ld_sd_mem(ld_sd_mem, entry):
    ld_sd_mem.busy = 1
    ld_sd_mem.cycle = 0
    ld_sd_mem.address = entry.address
    ld_sd_mem.dest_tag = entry.dest_tag
    ld_sd_mem.op = entry.op
    if ld_sd_mem.op == 'Sd':
        ld_sd_mem.data = entry.data

# function: only the ROB head may start its store access
def check_if_sd_committable(ld_sd_queue, ROB):
    return bool(ld_sd_queue and ROB
                and ld_sd_queue[0].op == 'Sd'
                and ld_sd_queue[0].dest_tag == ROB[0].ROB_tag
                and not ROB[0].store_complete)

# function: mem 
def mem(ld_sd_queue, ld_sd_mem, time_ld_sd_mem, results_buffer, 
        memory, ROB, cycle):
    '''look forward check for all Ld instructions'''
    remove_list = []
    for index, element in enumerate(ld_sd_queue):
        if (index>=1)&(element.op=='Ld')&(element.ready==1):
            data = forward_check_from_sd(ld_sd_queue, index)
            if len(data)>0:
                # Ld gets data 
                results_buffer.append(fu_result())
                results_buffer[-1].value = data[0]
                results_buffer[-1].dest_tag = element.dest_tag
                # remove the Ld instruction
                remove_list.append(element)
                # write mem cylce in ROB
                rob_index = find_ROB_entry(ROB, element.dest_tag)
                ROB[rob_index].mem.append(cycle)
    # remove lookforwared Ld
    for element in remove_list:
        ld_sd_queue.remove(element)
    '''ld_sd_mem execution'''
    if ld_sd_mem.busy == 1:
        # write mem starting cycle 
        if ld_sd_mem.cycle == 0:
            index = find_ROB_entry(ROB, ld_sd_mem.dest_tag)
            ROB[index].mem.extend([cycle, cycle+time_ld_sd_mem-1])
        
        # cycle ++
        ld_sd_mem.cycle +=1
        # get the data for Ld or reach the memory for Sd
        if ld_sd_mem.cycle == time_ld_sd_mem:
            ld_sd_mem.busy = 0
            if ld_sd_mem.op == 'Ld': 
                # put Ld data into results_buffer
                address = ld_sd_mem.address 
                data = memory[address]
                results_buffer.append(fu_result())
                results_buffer[-1].value = data
                results_buffer[-1].dest_tag = ld_sd_mem.dest_tag
            # Store data becomes architectural only in the COMMIT stage.
            else:
                index = find_ROB_entry(ROB, ld_sd_mem.dest_tag)
                ROB[index].store_complete = True

    '''fetch new instruction into ld_sd_mem'''
    if (ld_sd_mem.busy==0)&(len(ld_sd_queue)>0):
        # flag_1st_ldsd
        flag_1st_ldsd_sent = False 
        # fetch the ld_sd_queue header if it's Sd, ready and to be committed
        if (ld_sd_queue[0].op=='Sd'):
            # check if this Sd is ready and to be commited 
            if (ld_sd_queue[0].ready==1):
                # A completed store stays queued until COMMIT removes it.
                if check_if_sd_committable(ld_sd_queue, ROB):
                    # already have data in Sd
                    if (type(ld_sd_queue[0].data)==int)|(type(ld_sd_queue[0].data)==float):
                        # put the Sd entry into ld_sd_mem
                        entry = ld_sd_queue[0]
                        put_entry_into_ld_sd_mem(ld_sd_mem, entry)
                        flag_1st_ldsd_sent = True
                        ld_sd_mem.busy = 1

        # if the 1st Sd is not sent to ld_sd_mem, or the 1st is not Sd
        if (flag_1st_ldsd_sent==False):
            for index in range(len(ld_sd_queue)):
                # ready Ld
                if (ld_sd_queue[index].op=='Ld')&(ld_sd_queue[index].ready==1):
                    # Bypass unrelated stores only when their addresses are known.
                    if check_all_previous_Sd_no_match(ld_sd_queue, index):
                        put_entry_into_ld_sd_mem(ld_sd_mem, ld_sd_queue[index])
                        ld_sd_queue.remove(ld_sd_queue[index])
                        ld_sd_mem.busy =1
                        break

