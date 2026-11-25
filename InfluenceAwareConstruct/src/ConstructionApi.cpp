#include "ConstructionApi.h"

#include <filesystem>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

#include "DataProc.h"
#include "Machine.h"

namespace {

std::string JsonEscape(const std::string &value) {
    std::ostringstream output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"':
                output << "\\\"";
                break;
            case '\\':
                output << "\\\\";
                break;
            case '\b':
                output << "\\b";
                break;
            case '\f':
                output << "\\f";
                break;
            case '\n':
                output << "\\n";
                break;
            case '\r':
                output << "\\r";
                break;
            case '\t':
                output << "\\t";
                break;
            default:
                if (character < 0x20) {
                    output << "\\u"
                           << std::hex
                           << std::setw(4)
                           << std::setfill('0')
                           << static_cast<int>(character)
                           << std::dec;
                } else {
                    output << character;
                }
        }
    }
    return output.str();
}

void AppendMetricJson(
    std::ostringstream &output,
    const InitialMethodMetrics &metrics,
    const bool trailing_comma) {
    output << "{"
           << "\"makespan\":" << metrics.makespan << ","
           << "\"delivery_cost\":" << metrics.cost << ","
           << "\"total_energy\":" << metrics.energy << ","
           << "\"combined_objective\":"
           << std::setprecision(12)
           << metrics.combined_objective
           << "}";
    if (trailing_comma) {
        output << ",";
    }
}

std::string FileName(const std::string &path) {
    return std::filesystem::path(path).filename().string();
}

int AggregateTransportTime(const ConstructionResult &result) {
    if (Machine::transport_time_matrix.empty()) {
        return 0;
    }
    std::unordered_map<long long, int> machine_by_process;
    for (const auto &machine_items :
         result.schedule.get_schedule_items()) {
        for (const auto &operation : machine_items.schedule_process) {
            const long long key =
                (static_cast<long long>(operation.job_id) << 32) ^
                static_cast<unsigned int>(operation.process_id);
            machine_by_process[key] = machine_items.machine_id;
        }
    }
    int total = 0;
    for (const auto &job : result.jobs) {
        int previous_machine = -1;
        for (int operation_id = 0;
             operation_id < job.get_process_count();
             ++operation_id) {
            const long long key =
                (static_cast<long long>(job.get_job_id()) << 32) ^
                static_cast<unsigned int>(operation_id);
            const auto machine_it = machine_by_process.find(key);
            if (machine_it == machine_by_process.end()) {
                continue;
            }
            const int machine_id = machine_it->second;
            if (previous_machine >= 0 &&
                previous_machine != machine_id) {
                total += Machine::transport_time_matrix
                    [previous_machine][machine_id];
            }
            previous_machine = machine_id;
        }
    }
    return total;
}

}  // namespace

ConstructionResult ConstructFromDataset(const ConstructionConfig &config) {
    if (config.raw_file.empty()) {
        throw std::invalid_argument("Construction raw_file is required.");
    }
    const std::string method = NormalizeInitialMethodName(config.method);
    if (method.empty()) {
        std::ostringstream message;
        message << "Unsupported method '" << config.method << "'. Available:";
        for (const auto &name : InitialMethodNames()) {
            message << " " << name;
        }
        throw std::invalid_argument(message.str());
    }

    std::vector<Machine> machines;
    std::vector<Job> jobs;
    std::vector<Order> orders;
    Init(
        machines,
        jobs,
        orders,
        config.raw_file,
        config.additional_file,
        config.delivery_cost_file);

    std::vector<std::string> job_list;
    OrderToJobList(orders, job_list);
    if (job_list.empty()) {
        throw std::runtime_error(
            "The dataset does not contain any schedulable jobs.");
    }

    std::vector<Machine> fifo_machines = machines;
    Schedule fifo = RunInitialMethod(
        "FIFO_SPT",
        jobs,
        fifo_machines,
        job_list);
    fifo.set_fifo_total_time(fifo.get_TotalTime());
    fifo.set_fifo_earliness_tardiness_cost(
        fifo.get_total_earliness_tardiness_cost());
    fifo.set_fifo_energy_cost(fifo.get_total_energy_cost());
    CalculateCombinedObjective(fifo);

    std::vector<Machine> method_machines = machines;
    Schedule schedule = RunInitialMethod(
        method,
        jobs,
        method_machines,
        job_list);
    schedule.set_fifo_total_time(fifo.get_fifo_total_time());
    schedule.set_fifo_earliness_tardiness_cost(
        fifo.get_fifo_earliness_tardiness_cost());
    schedule.set_fifo_energy_cost(fifo.get_fifo_energy_cost());
    CalculateCombinedObjective(schedule);

    ConstructionResult result;
    result.config = config;
    result.config.method = method;
    result.method = method;
    result.jobs = jobs;
    result.schedule = schedule;
    result.metrics = {
        method,
        schedule.get_TotalTime(),
        schedule.get_total_earliness_tardiness_cost(),
        schedule.get_total_energy_cost(),
        schedule.get_combined_objective(),
    };
    result.fifo_baseline = {
        "FIFO_SPT",
        fifo.get_TotalTime(),
        fifo.get_total_earliness_tardiness_cost(),
        fifo.get_total_energy_cost(),
        fifo.get_combined_objective(),
    };
    return result;
}

std::string ConstructionResultToJson(const ConstructionResult &result) {
    const Schedule &schedule = result.schedule;
    const auto &process_list = schedule.get_processList();
    const auto &start_times = schedule.get_start_time();
    std::unordered_map<std::string, int> process_index;
    process_index.reserve(process_list.size());
    for (int index = 0; index < static_cast<int>(process_list.size()); ++index) {
        process_index[process_list[index]] = index;
    }

    int operation_count = 0;
    int processing_time = 0;
    for (const auto &machine_items : schedule.get_schedule_items()) {
        operation_count += static_cast<int>(
            machine_items.schedule_process.size());
        for (const auto &operation : machine_items.schedule_process) {
            processing_time += GetProcessTime(
                result.jobs,
                machine_items.machine_id,
                operation.job_id,
                operation.process_id);
        }
    }
    const int transport_time = AggregateTransportTime(result);

    std::ostringstream output;
    output << std::setprecision(12);
    output << "{"
           << "\"success\":true,"
           << "\"instance\":\""
           << JsonEscape(FileName(result.config.raw_file))
           << "\","
           << "\"method\":\""
           << JsonEscape(result.method)
           << "\","
           << "\"dataset\":{"
           << "\"root\":\""
           << JsonEscape(result.config.dataset_root)
           << "\","
           << "\"raw_file\":\""
           << JsonEscape(result.config.raw_file)
           << "\","
           << "\"additional_file\":\""
           << JsonEscape(result.config.additional_file)
           << "\","
           << "\"delivery_cost_file\":\""
           << JsonEscape(result.config.delivery_cost_file)
           << "\""
           << "},"
           << "\"objectives\":";
    AppendMetricJson(output, result.metrics, true);
    output << "\"objective_breakdown\":{"
           << "\"makespan\":" << schedule.get_TotalTime() << ","
           << "\"processing_time\":" << processing_time << ","
           << "\"transport_time\":" << transport_time << ","
           << "\"delivery_cost\":"
           << schedule.get_total_earliness_tardiness_cost() << ","
           << "\"total_energy\":"
           << schedule.get_total_energy_cost() << ","
           << "\"processing_energy\":"
           << schedule.get_total_processing_energy() << ","
           << "\"transport_energy\":"
           << schedule.get_total_transportation_energy() << ","
           << "\"combined_objective\":"
           << schedule.get_combined_objective()
           << "},"
           << "\"fifo_baseline\":";
    AppendMetricJson(output, result.fifo_baseline, true);
    output << "\"schedule\":{"
           << "\"machine_count\":" << schedule.get_machine_count() << ","
           << "\"job_count\":" << result.jobs.size() << ","
           << "\"operation_count\":" << operation_count << ","
           << "\"operations\":[";

    bool first_operation = true;
    for (const auto &machine_items : schedule.get_schedule_items()) {
        int sequence = 0;
        for (const auto &operation : machine_items.schedule_process) {
            const std::string key =
                std::to_string(operation.job_id) + "-" +
                std::to_string(operation.process_id);
            const auto index_it = process_index.find(key);
            const int start_time =
                index_it == process_index.end() ||
                index_it->second >= static_cast<int>(start_times.size())
                    ? 0
                    : start_times[index_it->second];
            const int duration = GetProcessTime(
                result.jobs,
                machine_items.machine_id,
                operation.job_id,
                operation.process_id);
            if (!first_operation) {
                output << ",";
            }
            first_operation = false;
            output << "{"
                   << "\"machine_id\":" << machine_items.machine_id << ","
                   << "\"sequence\":" << sequence << ","
                   << "\"job_id\":" << operation.job_id << ","
                   << "\"operation_id\":" << operation.process_id << ","
                   << "\"start_time\":" << start_time << ","
                   << "\"end_time\":" << (start_time + duration)
                   << "}";
            ++sequence;
        }
    }
    output << "]}}";
    return output.str();
}
