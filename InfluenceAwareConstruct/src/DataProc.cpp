//
// Created by luopw on 24-12-1.
//

#include "DataProc.h"
#include "Schedule.h"

#include <array>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <iomanip>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <cmath>

namespace {

std::string BuildProcessKey(const int job_id, const int process_id) {
    return std::to_string(job_id) + "-" + std::to_string(process_id);
}

struct ProcessRouteInfo {
    int index = -1;
    int machine_id = -1;
};

std::unordered_map<std::string, const Job *> BuildJobNameMap(const std::vector<Job> &jobs) {
    std::unordered_map<std::string, const Job *> job_name_map;
    job_name_map.reserve(jobs.size());
    for (const auto &job : jobs) {
        job_name_map[job.get_job_name()] = &job;
    }
    return job_name_map;
}

std::unordered_map<int, const Job *> BuildJobIdMap(const std::vector<Job> &jobs) {
    std::unordered_map<int, const Job *> job_id_map;
    job_id_map.reserve(jobs.size());
    for (const auto &job : jobs) {
        job_id_map[job.get_job_id()] = &job;
    }
    return job_id_map;
}

std::unordered_map<long long, int> BuildProcessTimeMap(const std::vector<Job> &jobs) {
    std::unordered_map<long long, int> process_time_map;
    for (const auto &job : jobs) {
        const auto job_processes = job.get_job_process();
        for (const auto &job_process : job_processes) {
            for (const auto &item : job_process.process_item) {
                const long long key =
                    (static_cast<long long>(job.get_job_id()) << 32) ^
                    (static_cast<long long>(item.process_id) << 16) ^
                    static_cast<unsigned int>(item.machine_id);
                process_time_map[key] = item.process_time;
            }
        }
    }
    return process_time_map;
}

long long BuildProcessTimeKey(const int job_id, const int process_id, const int machine_id) {
    return (static_cast<long long>(job_id) << 32) ^
           (static_cast<long long>(process_id) << 16) ^
           static_cast<unsigned int>(machine_id);
}

std::unordered_map<long long, int> BuildProcessEnergyMap(const std::vector<Job> &jobs) {
    std::unordered_map<long long, int> process_energy_map;
    for (const auto &job : jobs) {
        const auto job_processes = job.get_job_process();
        for (const auto &job_process : job_processes) {
            for (const auto &item : job_process.process_item) {
                const long long key =
                    (static_cast<long long>(job.get_job_id()) << 32) ^
                    (static_cast<long long>(item.process_id) << 16) ^
                    static_cast<unsigned int>(item.machine_id);
                process_energy_map[key] = item.processing_energy;
            }
        }
    }
    return process_energy_map;
}

std::string InferAdditionalFilePath(const std::string &raw_path) {
    namespace fs = std::filesystem;
    const fs::path raw(raw_path);
    for (fs::path directory = raw.parent_path();
         !directory.empty();
         directory = directory.parent_path()) {
        const std::string name = directory.filename().string();
        if (name.rfind("raw", 0) != 0) {
            if (directory == directory.root_path()) {
                break;
            }
            continue;
        }
        const std::string add_directory = "add" + name.substr(3);
        const fs::path relative = raw.lexically_relative(directory);
        return (
            directory.parent_path() / add_directory / relative
        ).string();
    }
    return raw_path;
}

std::string InferDeliveryCostFilePath(
    const std::string &additional_path,
    const std::string &delivery_cost_file) {
    namespace fs = std::filesystem;
    if (!delivery_cost_file.empty()) {
        return delivery_cost_file;
    }
    const fs::path additional(additional_path);
    const fs::path inferred =
        additional.parent_path().parent_path() /
        "delivery_cost" /
        additional.filename();
    return fs::is_regular_file(inferred) ? inferred.string() : "";
}

std::vector<std::array<int, 5>> ReadDeliveryCostFeatures(
    const std::string &delivery_cost_file,
    const int job_num) {
    std::ifstream input(delivery_cost_file);
    if (!input) {
        throw std::runtime_error(
            "Cannot open delivery-cost input file: " + delivery_cost_file);
    }
    std::vector<std::array<int, 5>> features;
    features.reserve(job_num);
    std::string line;
    while (std::getline(input, line)) {
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos || line[first] == '#') {
            continue;
        }
        std::istringstream row(line);
        std::array<int, 5> values{};
        for (auto &value : values) {
            if (!(row >> value)) {
                throw std::runtime_error(
                    "Invalid delivery-cost row: " + line);
            }
        }
        features.push_back(values);
    }
    if (static_cast<int>(features.size()) != job_num) {
        throw std::runtime_error(
            "Delivery-cost row count mismatch for " + delivery_cost_file);
    }
    return features;
}

}  // namespace


void Init(
    std::vector<Machine> &machines,
    std::vector<Job> &jobs,
    std::vector<Order> &orders,
    const std::string &file_path,
    const std::string &additional_file_path,
    const std::string &delivery_cost_file) {
    machines.clear();
    jobs.clear();
    orders.clear();

    const std::string raw_path = file_path;
    const std::string add_path = additional_file_path.empty()
        ? InferAdditionalFilePath(raw_path)
        : additional_file_path;
    const std::string delivery_path = InferDeliveryCostFilePath(
        add_path,
        delivery_cost_file);

    std::ifstream raw_in(raw_path);
    if (!raw_in) {
        throw std::runtime_error(
            "Cannot open raw input file: " + raw_path);
    }

    std::ifstream add_in(add_path);
    if (!add_in) {
        throw std::runtime_error(
            "Cannot open add input file: " + add_path);
    }

    int machineNum = 0, jobNum = 0;
    double maxProcessCount = 0.0;
    raw_in >> jobNum >> machineNum >> maxProcessCount;

    for (int i = 0; i < jobNum; i++) {
        Job jobItem;
        int processCount;
        raw_in >> processCount;
        jobItem.set_process_count(processCount);
        jobItem.set_job_id(i);
        jobItem.set_job_name("job" + std::to_string(i));
        std::vector<Job_process> jobProcess;
        for (int j = 0; j < processCount; j++) {
            Job_process jobProcessItem;
            int machineCount;
            raw_in >> machineCount;
            jobProcessItem.machine_count = machineCount;
            for (int k = 0; k < machineCount; k++) {
                Process_item processItem;
                int raw_machine_id;
                raw_in >> raw_machine_id >> processItem.process_time;
                processItem.machine_id = raw_machine_id - 1;
                processItem.process_id = j;
                processItem.processing_energy = 0;
                jobProcessItem.process_item.push_back(processItem);
            }
            jobProcess.push_back(jobProcessItem);
        }
        jobItem.set_job_process(jobProcess);
        jobs.push_back(jobItem);
    }

    for (int i = 0; i < jobNum; i++) {
        int processCount;
        add_in >> processCount;
        if (processCount != jobs[i].get_process_count()) {
            throw std::runtime_error(
                "Raw and add files contain different operation counts.");
        }
        auto job_process = jobs[i].get_job_process();
        for (int j = 0; j < processCount; j++) {
            int machineCount;
            add_in >> machineCount;
            if (machineCount !=
                static_cast<int>(job_process[j].process_item.size())) {
                throw std::runtime_error(
                    "Raw and add files contain different machine option counts.");
            }
            for (int k = 0; k < machineCount; k++) {
                int raw_machine_id, processing_energy;
                add_in >> raw_machine_id >> processing_energy;
                int machine_id = raw_machine_id - 1;
                bool matched = false;
                for (auto &item : job_process[j].process_item) {
                    if (item.machine_id == machine_id) {
                        item.processing_energy = processing_energy;
                        matched = true;
                        break;
                    }
                }
                if (!matched) {
                    throw std::runtime_error(
                        "Add file references a machine absent from the raw file.");
                }
            }
        }
        jobs[i].set_job_process(job_process);
    }

    if (add_in.fail()) {
        throw std::runtime_error(
            "Unexpected end of add input file: " + add_path);
    }

    std::vector<Order_item> orderItems;
    std::vector<std::array<int, 5>> delivery_features;
    if (!delivery_path.empty()) {
        delivery_features = ReadDeliveryCostFeatures(delivery_path, jobNum);
    }
    for (int i = 0; i < jobNum; i++) {
        Order_item orderItemItem;
        orderItemItem.job_name = "job" + std::to_string(i);
        orderItemItem.job_count = 1;
        if (!delivery_path.empty()) {
            const auto &features = delivery_features[i];
            orderItemItem.priority = features[0];
            orderItemItem.ready_time = features[1];
            orderItemItem.due_time = features[2];
            orderItemItem.earliness_cost = features[3];
            orderItemItem.tardiness_cost = features[4];
        } else {
            add_in >> orderItemItem.priority >> orderItemItem.ready_time
                   >> orderItemItem.due_time
                   >> orderItemItem.earliness_cost
                   >> orderItemItem.tardiness_cost;
        }
        jobs[i].set_ready_time(orderItemItem.ready_time);
        jobs[i].set_due_time(orderItemItem.due_time);
        jobs[i].set_earliness_cost(orderItemItem.earliness_cost);
        jobs[i].set_tardiness_cost(orderItemItem.tardiness_cost);
        jobs[i].set_weight(orderItemItem.priority);
        orderItems.push_back(orderItemItem);
    }

    Machine::transport_time_matrix.resize(machineNum, std::vector<int>(machineNum));
    for (int i = 0; i < machineNum; i++) {
        for (int j = 0; j < machineNum; j++) {
            if (!(add_in >> Machine::transport_time_matrix[i][j])) {
                throw std::runtime_error(
                    "Missing transport-time matrix values in: " + add_path);
            }
        }
    }

    Machine::transport_energy_matrix.resize(machineNum, std::vector<int>(machineNum));
    for (int i = 0; i < machineNum; i++) {
        for (int j = 0; j < machineNum; j++) {
            if (!(add_in >> Machine::transport_energy_matrix[i][j])) {
                throw std::runtime_error(
                    "Missing transport-energy matrix values in: " + add_path);
            }
        }
    }

    for (int i = 0; i < machineNum; i++) {
        Machine machineItem;
        machineItem.set_machine_id(i);
        machineItem.set_machine_name("machine" + std::to_string(i));
        machineItem.set_machine_type(Machine_type::Job_shop_multi_process_machine);
        machineItem.set_count(1);
        machineItem.set_idle_count(1);
        machines.push_back(machineItem);
    }

    Order orderItem;
    orderItem.set_order_id("order0");
    orderItem.set_order_items(orderItems);
    orders.push_back(orderItem);
}

void OrderToJobList(const std::vector<Order> &orders, std::vector<std::string> &jobList) {
    for (auto &orderItem : orders) {
        for (auto &[job_name, job_count, priority, ready_time, due_time, earliness_cost, tardiness_cost] : orderItem.get_order_items()) {
            for (int i=0;i<job_count;i++) {
                jobList.push_back(job_name);
            }
        }
    }
}

Schedule GenerateSolution(std::string file_path, const std::vector<std::string> &jobList, const std::vector<Job> &jobs, std::vector<Machine> &machines)
{
    Schedule schedule;
    std::string inputFilePath = file_path;
    // std::cout << "Input file path: " << inputFilePath << std::endl;
    if (inputFilePath.empty())
    {
        std::cerr << "Error: Input file path is empty." << std::endl;
        return schedule;
    }
    std::ifstream in(inputFilePath);
    std::cin.rdbuf(in.rdbuf());
    if (!in)
    {
        std::cerr << "Error: Cannot open input file: " << inputFilePath << std::endl;
        return schedule;
    }
    int machineNum = 0;
    std::cin >> machineNum;
    schedule.set_machine_count(machineNum);
    schedule.set_schedule_id(0);

    std::vector<Schedule_item> temp_schedule_items;

    for (int i = 0; i < machineNum; i++)
    {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        int ope_num = 0;
        std::cin >> ope_num;
        scheduleItem.process_count = ope_num;
        for (int j = 0; j < ope_num; j++)
        {
            int job_id = 0, process_id = 0;
            std::cin >> job_id >> process_id;
            Schedule_process scheduleProcess;
            scheduleProcess.job_id = job_id;
            scheduleProcess.process_id = process_id;
            scheduleItem.schedule_process.push_back(scheduleProcess);
        }
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);
    // 输出schedule items
    // for (auto &item : temp_schedule_items) {
    //     std::cout << "Machine ID: " << item.machine_id << ", Process Count: " << item.process_count << std::endl;
    //     for (auto &process : item.schedule_process) {
    //         std::cout << "  Job ID: " << process.job_id << ", Process ID: " << process.process_id << std::endl;
    //     }
    // }
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_schedule_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

// ReSharper disable once CppParameterMayBeConstPtrOrRef
Schedule GenerateInitialSolution(const std::vector<std::string> &jobList, const std::vector<Job> &jobs, std::vector<Machine> &machines) {
    Schedule schedule;
    const int machineNum = machines.size();
    schedule.set_machine_count(machineNum);
    auto temp_schedule_items = std::vector<Schedule_item>();
    for (int i = 0; i < machineNum; i++) {
        Schedule_item scheduleItem;
        scheduleItem.machine_id = i;
        scheduleItem.process_count = 0;
        scheduleItem.schedule_process.clear();
        temp_schedule_items.push_back(scheduleItem);
    }
    schedule.set_schedule_items(temp_schedule_items);

    for (auto &jobName : jobList) {
        // std::cout << "jobName: " << jobName << std::endl;
        auto job = SelectJobByJobName(jobs, jobName);
        // job.to_string();
        if (job.get_job_name() == "") {
            std::cout << "Error: Cannot find job by job name." << std::endl;
            return Schedule();
        }
        for (auto &[machine_count, process_item] : job.get_job_process()) {
            // 遍历获取工序数量最少的机器的id
            int temp_machine_id = process_item[0].machine_id;
            int machine_with_min_process_count = machines[temp_machine_id].get_process_count();
            for (int i = 1; i < process_item.size(); i++) {
                for (auto machine : machines) {
                    if (machine.get_machine_id() == process_item[i].machine_id) {
                        if (machine.get_process_count() < machine_with_min_process_count) {
                            temp_machine_id = process_item[i].machine_id;
                            machine_with_min_process_count = machine.get_process_count();
                        }
                    }
                }
            }
            int temp_machine_id_1 = temp_machine_id;
            double machine_with_min_failure_rate = machines[temp_machine_id_1].get_failure_rate();
            for (int i = 1; i < process_item.size(); i++) {
                for (auto machine : machines) {
                    if (machine.get_machine_id() == process_item[i].machine_id){
                        if (machine.get_process_count() == machine_with_min_process_count){
                            if (machine.get_failure_rate() < machine_with_min_failure_rate){
                                temp_machine_id_1 = process_item[i].machine_id;
                                machine_with_min_failure_rate = machine.get_failure_rate();
                            }
                        }
                    }
                }
            }
            schedule.AddProcess(temp_machine_id_1, job.get_job_id(), process_item[0].process_id);
            // 将temp_machine_id对应的机器的process_count加1
            for (auto &machine : machines) {
                if (machine.get_machine_id() == temp_machine_id_1) {
                    machine.set_process_count(machine.get_process_count() + 1);
                    break;
                }
            }
        }
    }
    std::vector<Schedule_item> temp_items = schedule.get_schedule_items();
    std::vector<std::vector<int>> graph = ScheduleItemsToGraph(schedule, temp_items, jobs, jobList, true, machines);
    schedule.set_schedule_id(0);
    return schedule;
}

Job SelectJobByJobName(const std::vector<Job> &jobs, const std::string &jobName) {
    const std::string temp = jobName.substr(0, jobName.find('-'));
    for (auto &job : jobs) {
        if (job.get_job_name() == temp) {
            return job;
        }
    }
    return Job();
}

int GetProcessTime(const std::vector<Job> &jobs, const int machine_id, const int job_id, const int process_id) {
    for (const auto &job : jobs) {
        if (job.get_job_id() == job_id) {
            for (const auto &[machine_count, process_item] : job.get_job_process()) {
                for (const auto &[temp_process_id, temp_machine_id, temp_process_time, temp_processing_energy] : process_item) {
                    if (machine_id == temp_machine_id && process_id == temp_process_id) {
                        return temp_process_time;
                    }
                }
            }
        }
    }
    return 0;
}

std::vector<std::vector<int>> ScheduleItemsToGraph(Schedule &schedule, std::vector<Schedule_item> &schedule_items, const std::vector<Job> &jobs, const std::vector<std::string> &jobList, const bool flag, std::vector<Machine> &machines) {
    std::vector<std::string> processList;
    int scheduled_process_count = 0;
    for (const auto &schedule_item : schedule_items) {
        scheduled_process_count += schedule_item.process_count;
    }
    processList.reserve(scheduled_process_count + 2);
    processList.push_back("start");
    std::unordered_map<std::string, ProcessRouteInfo> process_route_map;
    process_route_map.reserve(scheduled_process_count);
    for (const auto &schedule_item: schedule_items) {
        for (const auto &[job_id, process_id]: schedule_item.schedule_process) {
            const std::string process_key = BuildProcessKey(job_id, process_id);
            process_route_map[process_key] = {static_cast<int>(processList.size()), schedule_item.machine_id};
            processList.push_back(process_key);
        }
    }
    processList.push_back("end");
    const int processCount = processList.size();
    const int end_index = processCount - 1;
    const auto process_time_map = BuildProcessTimeMap(jobs);
    const auto job_name_map = BuildJobNameMap(jobs);

    std::unordered_map<int, const Job*> job_id_map;
    for (const auto &job : jobs) {
        job_id_map[job.get_job_id()] = &job;
    }

    std::vector<std::vector<int>> graph(processCount, std::vector<int>(processCount, -1));

    for (const auto &schedule_item: schedule_items) {
        for (int i = 0; i < schedule_item.schedule_process.size(); ++i) {
            const int job_id = schedule_item.schedule_process[i].job_id;
            const int process_id = schedule_item.schedule_process[i].process_id;
            const int index1 = process_route_map[BuildProcessKey(job_id, process_id)].index;
            if (i == 0 && process_id == 0) {
                int ready_time = 0;
                if (job_id_map.count(job_id)) {
                    ready_time = job_id_map[job_id]->get_ready_time();
                }
                graph[0][index1] = ready_time;
            }
            if (i == schedule_item.schedule_process.size() - 1) {
                const auto process_time_it = process_time_map.find(BuildProcessTimeKey(job_id, process_id, schedule_item.machine_id));
                graph[index1][end_index] = process_time_it == process_time_map.end() ? 0 : process_time_it->second;
            }
            if (i != 0) {
                const int prev_job_id = schedule_item.schedule_process[i - 1].job_id;
                const int prev_process_id = schedule_item.schedule_process[i - 1].process_id;
                const int index2 = process_route_map[BuildProcessKey(prev_job_id, prev_process_id)].index;
                const auto process_time_it = process_time_map.find(BuildProcessTimeKey(prev_job_id, prev_process_id, schedule_item.machine_id));
                graph[index2][index1] = process_time_it == process_time_map.end() ? 0 : process_time_it->second;
            }
        }
    }

    for (const auto &job: jobList) {
        const auto job_it = job_name_map.find(job.substr(0, job.find('-')));
        if (job_it == job_name_map.end()) {
            continue;
        }
        const Job &jobItem = *job_it->second;
        const int job_id = jobItem.get_job_id();
        const int jobProcessCount = jobItem.get_process_count();
        for (int i = 0; i < jobProcessCount - 1; ++i) {
            const auto current_it = process_route_map.find(BuildProcessKey(job_id, i));
            const auto next_it = process_route_map.find(BuildProcessKey(job_id, i + 1));
            if (current_it == process_route_map.end() || next_it == process_route_map.end()) {
                continue;
            }
            const int current_machine_id = current_it->second.machine_id;
            const int next_machine_id = next_it->second.machine_id;
            const auto process_time_it = process_time_map.find(BuildProcessTimeKey(job_id, i, current_machine_id));
            int transport_time = 0;
            if (current_machine_id != next_machine_id && !Machine::transport_time_matrix.empty()) {
                transport_time = Machine::transport_time_matrix[current_machine_id][next_machine_id];
            }
            graph[current_it->second.index][next_it->second.index] =
                (process_time_it == process_time_map.end() ? 0 : process_time_it->second) + transport_time;
        }
        // 设置每个工件的最后一道工序到end的边
        const int last_process_id = jobProcessCount - 1;
        const auto last_it = process_route_map.find(BuildProcessKey(job_id, last_process_id));
        if (last_it != process_route_map.end()) {
            const int last_machine_id = last_it->second.machine_id;
            const auto process_time_it = process_time_map.find(BuildProcessTimeKey(job_id, last_process_id, last_machine_id));
            graph[last_it->second.index][end_index] = process_time_it == process_time_map.end() ? 0 : process_time_it->second;
        }
    }
    if (flag) {
        schedule.set_graph(graph);
        schedule.set_processList(processList);
        CalculateTotalTime(schedule);
        CalculateTotalFailureRate(schedule, machines);
        CalculateEarlinessTardinessCost(schedule, jobs);
        CalculateTotalEnergy(schedule, jobs, jobList);
        CalculateCombinedObjective(schedule);
    }
    return graph;
}

int CalculateTotalFailureRate(Schedule &schedule, const std::vector<Machine> &machines){
    double total_failure_rate = 0.0;
    const std::vector<Schedule_item> schedule_items = schedule.get_schedule_items();
    for (int i = 0; i < schedule_items.size(); i++) {
        const int machine_id = schedule_items[i].machine_id;
        for (const auto &machine : machines) {
            if (machine.get_machine_id() == machine_id) {
                total_failure_rate += machine.get_failure_rate() * schedule_items[i].process_count;
                break;
            }
        }
    }
    schedule.set_total_failure_rate(total_failure_rate);
    return total_failure_rate;
}

int CalculateTotalTime(Schedule &schedule) {
    const std::vector<std::vector<int>> &graph = schedule.get_graph();
    const int processCount = graph.size();
    std::vector<int> inDegree(processCount, 0);
    for (int i = 0; i < processCount; ++i) {
        for (int j = 0; j < processCount; ++j) {
            if (graph[i][j] != -1) {
                inDegree[j]++;
            }
        }
    }
    std::vector<int> startTime(processCount, 0);
    int visited_count = 0;
    std::queue<int> zeroInDegreeQueue;
    for (int i = 0; i < processCount; ++i) {
        if (inDegree[i] == 0) {
            zeroInDegreeQueue.push(i);
        }
    }
    while (!zeroInDegreeQueue.empty()) {
        const int temp = zeroInDegreeQueue.front();
        zeroInDegreeQueue.pop();
        ++visited_count;
        for (int i = 0; i < processCount; ++i) {
            if (graph[temp][i] != -1) {
                int new_time = startTime[temp] + graph[temp][i];
                if (new_time > startTime[i]) {
                    startTime[i] = new_time;
                }
                inDegree[i]--;
                if (inDegree[i] == 0) {
                    zeroInDegreeQueue.push(i);
                }
            }
        }
    }
    
    if (visited_count != processCount) {
        throw std::runtime_error("calculate time: The graph contains a cycle and cannot be topologically sorted.");
    }
    const int ans = processCount == 0 ? 0 : startTime[processCount - 1];
    schedule.set_start_time(startTime);
    schedule.set_TotalTime(ans);
    return ans;
}

void CalculateEarlinessTardinessCost(Schedule &schedule, const std::vector<Job> &jobs) {
    const std::vector<std::string> &processList = schedule.get_processList();
    const std::vector<int> &startTime = schedule.get_start_time();
    const std::vector<std::vector<int>> &graph = schedule.get_graph();
    const int processCount = processList.size();

    std::unordered_map<int, int> job_last_process_index;
    std::unordered_map<int, int> job_last_process_id;
    for (int i = 1; i < processCount - 1; ++i) {
        const std::string &process_key = processList[i];
        size_t dash_pos = process_key.find('-');
        if (dash_pos == std::string::npos) continue;
        int job_id = std::stoi(process_key.substr(0, dash_pos));
        int process_id = std::stoi(process_key.substr(dash_pos + 1));
        if (!job_last_process_id.count(job_id) || process_id > job_last_process_id[job_id]) {
            job_last_process_id[job_id] = process_id;
            job_last_process_index[job_id] = i;
        }
    }

    std::unordered_map<int, const Job*> job_id_map;
    for (const auto &job : jobs) {
        job_id_map[job.get_job_id()] = &job;
    }

    int total_earliness_tardiness_cost = 0;

    for (const auto &[job_id, last_process_index] : job_last_process_index) {
        if (!job_id_map.count(job_id)) continue;
        const Job &job = *job_id_map[job_id];
        int completion_time = startTime[last_process_index];
        int process_time = 0;
        const int end_index = processCount - 1;
        if (graph[last_process_index][end_index] != -1) {
            process_time = graph[last_process_index][end_index];
        } else {
            for (int j = 0; j < processCount; ++j) {
                if (graph[last_process_index][j] != -1) {
                    process_time = graph[last_process_index][j];
                    break;
                }
            }
        }
        completion_time += process_time;

        int due_time = job.get_due_time();
        int earliness_cost = job.get_earliness_cost();
        int tardiness_cost = job.get_tardiness_cost();
        int weight = job.get_weight();

        int earliness = 0;
        int tardiness = 0;
        if (completion_time < due_time) {
            earliness = due_time - completion_time;
        } else if (completion_time > due_time) {
            tardiness = completion_time - due_time;
        }

        int job_cost = weight * (earliness * earliness_cost + tardiness * tardiness_cost);
        total_earliness_tardiness_cost += job_cost;
    }

    schedule.set_total_earliness_tardiness_cost(total_earliness_tardiness_cost);
}

void CalculateTotalEnergy(Schedule &schedule, const std::vector<Job> &jobs, const std::vector<std::string> &jobList) {
    const auto process_energy_map = BuildProcessEnergyMap(jobs);
    const auto job_name_map = BuildJobNameMap(jobs);
    const auto &schedule_items = schedule.get_schedule_items();

    std::unordered_map<std::string, std::pair<int, int>> process_machine_map;
    for (const auto &schedule_item : schedule_items) {
        for (const auto &[job_id, process_id] : schedule_item.schedule_process) {
            const std::string key = BuildProcessKey(job_id, process_id);
            process_machine_map[key] = {schedule_item.machine_id, job_id};
        }
    }

    int total_processing_energy = 0;
    int total_transportation_energy = 0;

    for (const auto &job_name : jobList) {
        const auto job_it = job_name_map.find(job_name.substr(0, job_name.find('-')));
        if (job_it == job_name_map.end()) {
            continue;
        }
        const Job &jobItem = *job_it->second;
        const int job_id = jobItem.get_job_id();
        const int jobProcessCount = jobItem.get_process_count();

        int prev_machine_id = -1;
        for (int i = 0; i < jobProcessCount; ++i) {
            const std::string process_key = BuildProcessKey(job_id, i);
            if (!process_machine_map.count(process_key)) {
                continue;
            }
            const int current_machine_id = process_machine_map[process_key].first;

            const long long energy_key = BuildProcessTimeKey(job_id, i, current_machine_id);
            if (process_energy_map.count(energy_key)) {
                total_processing_energy += process_energy_map.at(energy_key);
            }

            if (prev_machine_id != -1 && prev_machine_id != current_machine_id && !Machine::transport_energy_matrix.empty()) {
                total_transportation_energy += Machine::transport_energy_matrix[prev_machine_id][current_machine_id];
            }
            prev_machine_id = current_machine_id;
        }
    }

    schedule.set_total_processing_energy(total_processing_energy);
    schedule.set_total_transportation_energy(total_transportation_energy);
    schedule.set_total_energy_cost(total_processing_energy + total_transportation_energy);
}

void CalculateCombinedObjective(Schedule &schedule) {
    if (schedule.get_fifo_total_time() == 0 || 
        schedule.get_fifo_earliness_tardiness_cost() == 0 || 
        schedule.get_fifo_energy_cost() == 0) {
        schedule.set_combined_objective(0);
        return;
    }

    double ratio_time = static_cast<double>(schedule.get_TotalTime()) / schedule.get_fifo_total_time();
    double ratio_cost = static_cast<double>(schedule.get_total_earliness_tardiness_cost()) / schedule.get_fifo_earliness_tardiness_cost();
    double ratio_energy = static_cast<double>(schedule.get_total_energy_cost()) / schedule.get_fifo_energy_cost();

    double euclidean_distance = std::sqrt(ratio_time * ratio_time + ratio_cost * ratio_cost + ratio_energy * ratio_energy);
    schedule.set_combined_objective(euclidean_distance);
}

void PrintScheduleDetails(const Schedule &schedule, const std::vector<Job> &jobs) {
    const auto &schedule_items = schedule.get_schedule_items();
    const auto &start_time = schedule.get_start_time();
    const auto &processList = schedule.get_processList();
    const auto &graph = schedule.get_graph();
    const auto process_time_map = BuildProcessTimeMap(jobs);

    std::unordered_map<std::string, int> process_index_map;
    for (int i = 0; i < processList.size(); ++i) {
        process_index_map[processList[i]] = i;
    }

    std::cout << "=== Debug: Process List ===" << std::endl;
    for (int i = 0; i < processList.size(); ++i) {
        std::cout << "Index " << i << ": " << processList[i] << ", start_time=" << start_time[i] << std::endl;
    }
    
    std::cout << "=== Debug: Checking process_index_map ===" << std::endl;
    for (const auto &schedule_item : schedule_items) {
        for (const auto &[job_id, process_id] : schedule_item.schedule_process) {
            const std::string process_key = BuildProcessKey(job_id, process_id);
            auto it = process_index_map.find(process_key);
            if (it != process_index_map.end()) {
                int idx = it->second;
                std::cout << "Key '" << process_key << "' -> idx=" << idx 
                          << ", processList[idx]=" << processList[idx] 
                          << ", start_time[idx]=" << start_time[idx] << std::endl;
            }
        }
    }
    
    std::cout << "=== Debug: Process List (Repeated) ===" << std::endl;
    for (int i = 0; i < processList.size(); ++i) {
        std::cout << "Index " << i << ": " << processList[i] << ", start_time=" << start_time[i] << std::endl;
    }
    
    std::cout << "=== Debug: Schedule Items Mapping ===" << std::endl;
    for (const auto &schedule_item : schedule_items) {
        for (const auto &[job_id, process_id] : schedule_item.schedule_process) {
            const std::string process_key = BuildProcessKey(job_id, process_id);
            if (process_index_map.count(process_key)) {
                int index = process_index_map[process_key];
                std::cout << "Job " << job_id << " Process " << process_id 
                          << " -> key=" << process_key 
                          << " -> index=" << index 
                          << " -> start_time=" << start_time[index] 
                          << " -> machine=" << schedule_item.machine_id << std::endl;
            } else {
                std::cout << "Job " << job_id << " Process " << process_id 
                          << " -> key=" << process_key << " NOT FOUND!" << std::endl;
            }
        }
    }
    std::cout << "=== Debug: Last Process Mapping ===" << std::endl;

    std::unordered_map<std::string, int> process_machine_map;
    for (const auto &schedule_item : schedule_items) {
        for (const auto &[job_id, process_id] : schedule_item.schedule_process) {
            const std::string key = BuildProcessKey(job_id, process_id);
            process_machine_map[key] = schedule_item.machine_id;
        }
    }

    std::cout << "=== Detailed Schedule ===" << std::endl;
    std::cout << std::left << std::setw(8) << "Job" 
              << std::setw(10) << "Process" 
              << std::setw(8) << "Machine" 
              << std::setw(12) << "Start Time" 
              << std::setw(12) << "End Time" 
              << std::setw(12) << "Process Time" 
              << std::endl;
    std::cout << "------------------------------------------------------------------------" << std::endl;

    for (const auto &schedule_item : schedule_items) {
        for (const auto &[job_id, process_id] : schedule_item.schedule_process) {
            const std::string process_key = BuildProcessKey(job_id, process_id);
            const int machine_id = schedule_item.machine_id;
            const int index = process_index_map[process_key];
            const int start = start_time[index];
            
            const long long time_key = BuildProcessTimeKey(job_id, process_id, machine_id);
            int process_time = 0;
            if (process_time_map.count(time_key)) {
                process_time = process_time_map.at(time_key);
            }
            const int end = start + process_time;

            std::cout << std::left << std::setw(8) << ("job" + std::to_string(job_id)) 
                      << std::setw(10) << ("p" + std::to_string(process_id)) 
                      << std::setw(8) << ("m" + std::to_string(machine_id)) 
                      << std::setw(12) << start 
                      << std::setw(12) << end 
                      << std::setw(12) << process_time 
                      << std::endl;
        }
    }

    std::cout << "------------------------------------------------------------------------" << std::endl;

    std::cout << "\n=== Job Completion Details ===" << std::endl;
    std::cout << std::left << std::setw(8) << "Job" 
              << std::setw(12) << "Ready Time" 
              << std::setw(12) << "Due Time" 
              << std::setw(16) << "Completion Time" 
              << std::setw(12) << "Earliness" 
              << std::setw(12) << "Tardiness" 
              << std::setw(12) << "Weight" 
              << std::setw(14) << "Early Cost" 
              << std::setw(14) << "Tardy Cost" 
              << std::setw(16) << "Job Cost" 
              << std::endl;
    std::cout << "------------------------------------------------------------------------------------------------------------------------------------" << std::endl;

    std::unordered_map<int, int> job_last_process_index;
    std::unordered_map<int, int> job_last_process_id;
    for (int i = 1; i < processList.size() - 1; ++i) {
        const std::string &process_key = processList[i];
        size_t dash_pos = process_key.find('-');
        if (dash_pos == std::string::npos) continue;
        int job_id = std::stoi(process_key.substr(0, dash_pos));
        int process_id = std::stoi(process_key.substr(dash_pos + 1));
        if (!job_last_process_id.count(job_id) || process_id > job_last_process_id[job_id]) {
            job_last_process_id[job_id] = process_id;
            job_last_process_index[job_id] = i;
        }
    }

    std::unordered_map<int, const Job*> job_id_map;
    for (const auto &job : jobs) {
        job_id_map[job.get_job_id()] = &job;
    }

    int total_cost = 0;
    for (const auto &[job_id, last_process_index] : job_last_process_index) {
        if (!job_id_map.count(job_id)) continue;
        const Job &job = *job_id_map[job_id];
        
        int completion_time = start_time[last_process_index];
        const int end_index = graph.size() - 1;
        int process_time = 0;
        if (graph[last_process_index][end_index] != -1) {
            process_time = graph[last_process_index][end_index];
        } else {
            for (int j = 0; j < graph.size(); ++j) {
                if (graph[last_process_index][j] != -1) {
                    process_time = graph[last_process_index][j];
                    break;
                }
            }
        }
        completion_time += process_time;

        int due_time = job.get_due_time();
        int ready_time = job.get_ready_time();
        int earliness_cost = job.get_earliness_cost();
        int tardiness_cost = job.get_tardiness_cost();
        int weight = job.get_weight();

        int earliness = 0;
        int tardiness = 0;
        if (completion_time < due_time) {
            earliness = due_time - completion_time;
        } else if (completion_time > due_time) {
            tardiness = completion_time - due_time;
        }

        int job_cost = weight * (earliness * earliness_cost + tardiness * tardiness_cost);
        total_cost += job_cost;

        std::cout << std::left << std::setw(8) << ("job" + std::to_string(job_id)) 
                  << std::setw(12) << ready_time 
                  << std::setw(12) << due_time 
                  << std::setw(16) << completion_time 
                  << std::setw(12) << earliness 
                  << std::setw(12) << tardiness 
                  << std::setw(12) << weight 
                  << std::setw(14) << earliness_cost 
                  << std::setw(14) << tardiness_cost 
                  << std::setw(16) << job_cost 
                  << std::endl;
    }

    std::cout << "------------------------------------------------------------------------------------------------------------------------------------" << std::endl;
    std::cout << std::right << std::setw(148) << "Total Earliness-Tardiness Cost: " << total_cost << std::endl;
}

// 设置停止标志，当搜索时间超过指定时间或搜索次数超过指定次数时，停止搜索
bool CheckStopFlag(const int &search_time, const int &count, const int repeat_count, const int max_repeat_count) {
    const int now = time(nullptr);
    if (now - search_time > 6000) {  // 30000
        return false;
    }
    if (count > 1200) {
        return false;
    }
    if (repeat_count>max_repeat_count) {
        return false;
    }
    return true;
}


