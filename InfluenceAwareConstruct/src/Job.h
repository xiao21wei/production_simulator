//
// Created by luopw on 24-12-1.
//

#ifndef JOB_H
#define JOB_H
#include <string>
#include <vector>

struct Process_item {
    int process_id;  // process id,工序编号
    int machine_id;  // machine id,机器编号
    int process_time;  // process time,加工时间
    int processing_energy;  // processing energy,加工能耗
};

struct Job_process {  // 工序项
    int machine_count;  // machine count,机器数量
    std::vector<Process_item> process_item;  // process item,工序可选项
};

class Job {
    int job_id;  // job id,工件编号
    std::string job_name;  // job name,工件名称
    int process_count;  // process count,工序数量
    std::vector<Job_process> job_process;  // job process,工序
    int ready_time;  // ready time,就绪时间
    int due_time;  // due time,交付时间
    int earliness_cost;  // earliness cost,提前成本
    int tardiness_cost;  // tardiness cost,延迟成本
    int weight;  // weight,权重

public:
    Job();
    int get_job_id() const;
    const std::string &get_job_name() const;
    int get_process_count() const;
    const std::vector<Job_process> &get_job_process() const;
    int get_ready_time() const;
    int get_due_time() const;
    int get_earliness_cost() const;
    int get_tardiness_cost() const;
    int get_weight() const;
    void set_job_id(int job_id);
    void set_job_name(const std::string &job_name);
    void set_process_count(int process_count);
    void set_job_process(const std::vector<Job_process> &job_process);
    void set_ready_time(int ready_time);
    void set_due_time(int due_time);
    void set_earliness_cost(int earliness_cost);
    void set_tardiness_cost(int tardiness_cost);
    void set_weight(int weight);
    void to_string();

    int getTotalAverageProcessTime() const;
};

#endif //JOB_H
