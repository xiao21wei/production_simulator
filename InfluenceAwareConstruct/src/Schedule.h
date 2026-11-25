//
// Created by luopw on 24-12-1.
//

#ifndef SCHEDULE_H
#define SCHEDULE_H

#include <string>
#include <vector>

struct Schedule_process {
    int job_id;  // job id,工件编号
    int process_id; // process id,工序编号
};

struct Schedule_item {
    int machine_id;  // machine id,机器编号
    int process_count;  // process count,工序数量
    std::vector<Schedule_process> schedule_process;  // schedule process,调度工序
};

class Schedule {
    int schedule_id;  // schedule id,调度编号
    int machine_count;  // machine count,机器数量
    std::vector<Schedule_item> schedule_items;  // schedule items,调度项
    std::vector<std::string> processList;  // process list,工序列表
    std::vector<std::vector<int>> graph; // graph,邻接矩阵
    int TotalTime; // process time,加工时间
    std::vector<int> start_time;  // start time,开始时间
    std::vector<int> completion_time;  // completion time,完工时间
    double total_failure_rate = 0;  // total failure rate,总故障率
    int total_earliness_tardiness_cost = 0;  // total earliness and tardiness cost,总提前/延迟成本
    int total_processing_energy = 0;  // total processing energy,总加工能耗
    int total_transportation_energy = 0;  // total transportation energy,总运输能耗
    int total_energy_cost = 0;  // total energy cost,总能源开销
    int fifo_total_time = 0;  // FIFO_SPT total time, FIFO_SPT总完工时间
    int fifo_earliness_tardiness_cost = 0;  // FIFO_SPT earliness tardiness cost, FIFO_SPT总提前/延迟成本
    int fifo_energy_cost = 0;  // FIFO_SPT energy cost, FIFO_SPT总能源开销
    double combined_objective = 0;  // combined objective,联合优化目标（欧氏距离）

public:
    Schedule();
    int get_schedule_id() const;
    int get_machine_count() const;
    const std::vector<Schedule_item> &get_schedule_items() const;
    const std::vector<std::string> &get_processList() const;
    const std::vector<std::vector<int>> &get_graph() const;
    int get_TotalTime() const;
    const std::vector<int> &get_start_time() const;
    const std::vector<int> &get_completion_time() const;
    double get_total_failure_rate() const;
    int get_total_earliness_tardiness_cost() const;
    int get_total_processing_energy() const;
    int get_total_transportation_energy() const;
    int get_total_energy_cost() const;
    int get_fifo_total_time() const;
    int get_fifo_earliness_tardiness_cost() const;
    int get_fifo_energy_cost() const;
    double get_combined_objective() const;
    void set_schedule_id(int schedule_id);
    void set_machine_count(int machine_count);
    void set_schedule_items(const std::vector<Schedule_item> &schedule_items);
    void set_processList(const std::vector<std::string> &processList);
    void set_graph(const std::vector<std::vector<int>> &graph);
    void set_TotalTime(int ProcessTime);
    void set_start_time(const std::vector<int> &start_time);
    void set_completion_time(const std::vector<int> &completion_time);
    void set_total_failure_rate(double total_failure_rate);
    void set_total_earliness_tardiness_cost(int total_earliness_tardiness_cost);
    void set_total_processing_energy(int total_processing_energy);
    void set_total_transportation_energy(int total_transportation_energy);
    void set_total_energy_cost(int total_energy_cost);
    void set_fifo_total_time(int fifo_total_time);
    void set_fifo_earliness_tardiness_cost(int fifo_earliness_tardiness_cost);
    void set_fifo_energy_cost(int fifo_energy_cost);
    void set_combined_objective(double combined_objective);
    void to_string() const;

    void AddProcess(int machine_id, int job_id, int process_id);
    void ToMapCode() const;
    std::vector<std::string> GetKeyProcess() const;
};



#endif //SCHEDULE_H
