#ifndef CONSTRUCTION_API_H
#define CONSTRUCTION_API_H

#include <string>
#include <vector>

#include "Experiment.h"
#include "Job.h"
#include "Schedule.h"

struct ConstructionConfig {
    std::string method = "InfluenceAwareConstruct";
    std::string dataset_root;
    std::string raw_file;
    std::string additional_file;
    std::string delivery_cost_file;
};

struct ConstructionResult {
    ConstructionConfig config;
    std::string method;
    std::vector<Job> jobs;
    Schedule schedule;
    InitialMethodMetrics metrics;
    InitialMethodMetrics fifo_baseline;
};

// 根据数据集路径配置选择一个初始构造方法并生成完整 FJSP 调度。
ConstructionResult ConstructFromDataset(const ConstructionConfig &config);

// 将结构化调度结果序列化为稳定的 JSON，供模拟器 API 调用。
std::string ConstructionResultToJson(const ConstructionResult &result);

#endif  // CONSTRUCTION_API_H
