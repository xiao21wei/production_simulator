import random

def generate_instance(n_jobs, n_machines, seed):
    min_nop = 10                      # minimum number of operations per job
    max_nop = 20                      # maximum number of operations per job
    min_meq = 49                       # minimum number of available machines per operation
    max_meq = min(72, n_machines)     # maximum number of available machines per operation
    min_proct = 40                   # minimum processing time per operation
    max_proct = 60                   # maximum processing time per operation
    min_mot = -10                    # minimum offset time on per machine
    max_mot = 10                     # maximum offset time on per machine

    output_str = f"{n_jobs} {n_machines} "
    average_prot = (min_proct + max_proct) // 2
    output_str += f"{average_prot}\n"
    random.seed(seed)
    for i in range(n_jobs):
        n_operations = random.randint(min_nop, max_nop)
        output_str += f"{n_operations} "
        for j in range(n_operations):
            n_equipment = random.randint(min_meq, max_meq)
            output_str += f"{n_equipment} "
            machine_indices = random.sample(range(n_machines), n_equipment)
            for m in machine_indices:
                processing_time = random.randint(min_proct, max_proct)
                offset_time = random.randint(min_mot, max_mot)
                time = processing_time + offset_time
                output_str += f"{m} {time} "
        output_str += "\n"
    return output_str

if __name__ == "__main__":
    input = generate_instance(200, 120, seed=42)
    print(input)