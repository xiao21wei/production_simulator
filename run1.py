import os

for i in range(40, 210, 10):
    for j in range(i+55, 105+i, 5):
        run_cmd = f"python run.py {i} {j} >> result1.csv"
        print(run_cmd)
        os.system(run_cmd)