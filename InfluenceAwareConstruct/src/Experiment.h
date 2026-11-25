//
// Created by luopw on 25-5-1.
//

#ifndef EXPERIMENT_H
#define EXPERIMENT_H
#include <string>
#include <vector>

#include "Job.h"
#include "Machine.h"
#include "Schedule.h"

// FIFO：First in First Out  EET: Earliest End Time  SPT: Shortest Processing Time
Schedule FIFO_EET(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);
Schedule FIFO_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);

// MOPNR：Most Operation Number Remaining  EET: Earliest End Time  SPT: Shortest Processing Time
Schedule MOPNR_EET(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);
Schedule MOPNR_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);

// MWKR：Most Work Remaining   EET: Earliest End Time  SPT: Shortest Processing Time
Schedule MWKR_EET(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);
Schedule MWKR_SPT(std::vector<Job> &jobs, std::vector<Machine> &machines, std::vector<std::string> &jobList);

// 基于 method.md 多目标影响因素（运输耦合、关键路径、拥堵排队、订单优先级、能耗权衡）的快速构造法
Schedule InfluenceAwareConstruct(
    std::vector<Job> &jobs,
    std::vector<Machine> &machines,
    std::vector<std::string> &jobList);

struct InitialMethodMetrics {
    std::string method_name;
    int makespan = 0;
    int cost = 0;
    int energy = 0;
    double combined_objective = 0.0;
};

struct InitialComparisonResult {
    Schedule fifo_baseline;
    Schedule best_schedule;
    std::vector<InitialMethodMetrics> methods;
    std::string best_method;
};

// 返回支持的统一初始构造方法名称。
const std::vector<std::string> &InitialMethodNames();

// 将 InfluenceAware 等历史别名转换为统一方法名；未知方法返回空字符串。
std::string NormalizeInitialMethodName(const std::string &method_name);

// 按方法名称运行一种初始解构造方法。
Schedule RunInitialMethod(
    const std::string &method_name,
    std::vector<Job> &jobs,
    std::vector<Machine> &machines,
    std::vector<std::string> &jobList);

// 运行全部初始解构造方法，并以 FIFO_SPT 为基准计算 combined_objective
InitialComparisonResult CompareInitialMethods(
    std::vector<Job> &jobs,
    const std::vector<Machine> &machines_template,
    std::vector<std::string> &jobList);

#endif //EXPERIMENT_H
