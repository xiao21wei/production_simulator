import sys
from simulator.simulator import *
from model_predict.data.generate_machine_data import generate_machine_datasets


if "__main__" == __name__:
    # mtbf = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    # mttr = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    predict_threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.93
    
    failures = {}
    input_file = "input1.txt"

    simulator0 = Simulator()
    simulator0.init(input_file)
    simulator0.schedule_file = "result_schedule0.csv"
    simulator0.gantt_file = "gantt_chart0.txt"
    # simulator0.run()
    generate_machine_datasets(num_machines=len(simulator0.machines), min_len=10000, seed=42)

    # without failure prediction
    simulator1 = Simulator()
    simulator1.init(input_file)
    simulator1.addDetectEvent()
    simulator1.predict_threshold = predict_threshold
    simulator1.schedule_file = "result_schedule1.csv"
    simulator1.gantt_file = "gantt_chart1.txt"
    # simulator1.run()

    # with failure prediction
    simulator2 = Simulator()
    simulator2.init(input_file)
    simulator2.addPredictEvent()
    simulator2.addDetectEvent()
    simulator2.predict_threshold = predict_threshold
    simulator2.schedule_file = "result_schedule2.csv"
    simulator2.gantt_file = "gantt_chart2.txt"
    simulator2.run()
    

    # 优化幅度
    # improvement = ((simulator1.makespan - simulator2.makespan) / simulator1.makespan) * 100
    # if improvement > 20:
    #     print(f"{mtbf},{mttr},{time_horizon},{simulator1.makespan},{simulator2.makespan},{improvement:.2f}%    ******")
    # print(f"{mtbf},{mttr},{time_horizon},{simulator1.makespan},{simulator2.makespan},{improvement:.2f}%")

    # print("mtbf:", mtbf, "mttr:", mttr, "time_horizon:", time_horizon)
    print(f"Makespan with failures: {simulator1.makespan}")
    print(f"Makespan with predictions: {simulator2.makespan}")

# python run.py failure
# python run.py predict
